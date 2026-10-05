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
    # Calls the saas Skills API; listed only when SAAS_SKILLS_URL/KEY are set.
    needs_saas: bool = False
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
            "Find the articles most relevant to a question: semantic search "
            "over the article store, widened by the question's own keywords "
            "and reranked. Returns the articles with a breakdown of their "
            "sources, categories, sentiment and dates"
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
    "get_social_posts": ToolSpec(
        name="get_social_posts",
        description=(
            "Social posts about a monitored brand (X, Reddit, Instagram, TikTok, "
            "Bluesky) with relevance, sentiment, engagement and, for posts not "
            "written in English, the original text next to the translation. This "
            "is the Social tab's feed; the topic tools return news articles and "
            "leave these out."
        ),
        properties={
            "brand": {"type": "string", "description": "Brand display name as listed by list_brands / the Brand Watcher (e.g. 'Oviva')"},
            "topic": {"type": "string", "description": "Alternative to brand: the 'Brand Monitoring <brand>' topic name"},
            "days_back": {"type": "integer", "description": "Window in days (default 7)", "default": 7},
            "min_relevance": {"type": "number", "description": "Drop posts below this relevance (default 0.4, the Social tab's floor)", "default": 0.4},
            "platform": {"type": "string", "description": "Only one platform: twitter, reddit, instagram, tiktok, bluesky"},
            "sentiment": {"type": "string", "description": "Only one sentiment: positive, neutral, negative"},
            "limit": {"type": "integer", "description": "Maximum posts (default 100, max 500)", "default": 100},
            "include_owned": {"type": "boolean", "description": "Include the brand's own posts (never counted in sentiment)", "default": False},
        },
        timeout=30.0,
        max_bytes=_ARTICLE_LIST_BYTES,
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
    # ---- Brand Watcher (handlers in brand_tools.py; each says so when the
    # module is off on this site) ----
    "list_brands": ToolSpec(
        name="list_brands",
        description="The brands this site monitors (the primary brand and its competitors), with the markets each sits in. Call before the other brand tools.",
        properties={},
        timeout=15.0,
    ),
    "get_brand_stats": ToolSpec(
        name="get_brand_stats",
        description="Brand Watcher headline numbers for one brand: article counts, sentiment split, category distribution over a window. The Dashboard's stat cards.",
        properties={
            "brand": {"type": "string", "description": "Brand display name from list_brands (default: the primary brand)"},
            "brand_id": {"type": "integer"},
            "days_back": {"type": "integer", "description": "Window in days (default 90)", "default": 90},
        },
        timeout=60.0,
    ),
    "get_brand_articles": ToolSpec(
        name="get_brand_articles",
        description="Classified news articles about one brand: category, sentiment, risk flags. The Articles tab. Paged.",
        properties={
            "brand": {"type": "string", "description": "Brand display name from list_brands (default: the primary brand)"},
            "brand_id": {"type": "integer"},
            "categories": {"type": "string", "description": "Comma-separated category names to keep (e.g. 'Legal & Regulatory,Product')"},
            "days_back": {"type": "integer", "default": 30},
            "sort_by": {"type": "string", "description": "date (default) or relevance", "default": "date"},
            "page": {"type": "integer", "default": 1},
            "per_page": {"type": "integer", "description": "1-200 (default 25)", "default": 25},
        },
        timeout=60.0,
        max_bytes=_ARTICLE_LIST_BYTES,
    ),
    "get_brand_perception": ToolSpec(
        name="get_brand_perception",
        description="Perception across five surfaces for every brand: media, social, community (Reddit), employee (Glassdoor), investor. Net sentiment scores with volumes; the Perception tab.",
        properties={
            "days_back": {"type": "integer", "default": 90},
        },
        timeout=60.0,
    ),
    "get_brand_voices": ToolSpec(
        name="get_brand_voices",
        description=(
            "Who is talking about a brand and what each audience thinks: on-brand social and "
            "community posts grouped by the author's role (patient, clinician, caregiver, "
            "customer, academic, professional, employee, journalist, investor, brand, unknown) "
            "with a sentiment split per audience, the posts, and a model digest per audience "
            "with verbatim quotes. The Voices tab. Ask this for 'what do doctors think of us "
            "versus patients'."
        ),
        properties={
            "brand": {"type": "string", "description": "Brand display name from list_brands (default: the primary brand)"},
            "brand_id": {"type": "integer"},
            "days_back": {"type": "integer", "default": 90},
            "with_digest": {"type": "boolean", "description": "Also return the model digest (themes + quotes) per audience (default true)", "default": True},
            "roles": {"type": "string", "description": "Comma-separated roles to digest (default: the focus pair, e.g. clinician,patient)"},
            "posts_per_role": {"type": "integer", "description": "Posts returned per audience (default 20, max 60)", "default": 20},
        },
        timeout=_LLM_TIMEOUT * 2,
        max_bytes=_ARTICLE_LIST_BYTES,
    ),
    "get_brand_alerts": ToolSpec(
        name="get_brand_alerts",
        description="Recent Brand Watcher alert events (negative-social spikes, high-reach negative posts, news net-negative, category spikes, new critics, Glassdoor deterioration ...).",
        properties={
            "limit": {"type": "integer", "default": 50},
            "unacked_only": {"type": "boolean", "default": False},
        },
        timeout=30.0,
    ),
    # ---- Market Monitor ----
    "list_markets": ToolSpec(
        name="list_markets",
        description="The markets this site tracks, with vendor counts. Call before the other market tools.",
        properties={},
        timeout=15.0,
    ),
    "get_market_vendors": ToolSpec(
        name="get_market_vendors",
        description="The vendors in one market with their profile fields (headcount, funding, founded, identifiers) and collection state.",
        properties={
            "market": {"type": "string", "description": "Market name from list_markets (default: the first enabled market)"},
            "market_id": {"type": "integer"},
            "role": {"type": "string", "description": "vendor, watch or excluded (default: all but excluded)"},
            "collecting_only": {"type": "boolean", "default": False},
        },
        timeout=60.0,
    ),
    "get_market_analysis": ToolSpec(
        name="get_market_analysis",
        description="Cross-sectional market analyses: formation (founding years vs announcement volume), signal_noise (who announces vs who just posts), funding (stage mix, momentum, shared investors), hiring (what the market recruits for), share_of_voice. One by name, or all.",
        properties={
            "market": {"type": "string"},
            "market_id": {"type": "integer"},
            "name": {"type": "string", "description": "formation, signal_noise, funding, hiring or share_of_voice; omit for all"},
            "days": {"type": "integer", "description": "Window for the period-based analyses (1-365)"},
        },
        timeout=90.0,
    ),
    "get_market_top_voices": ToolSpec(
        name="get_market_top_voices",
        description="The outside accounts posting about a market, ranked by engagement, with their profiled market role (vendor, vendor staff, practitioner, press ...) and audience (patient, clinician, customer ...) where known.",
        properties={
            "market": {"type": "string"},
            "market_id": {"type": "integer"},
            "days": {"type": "integer", "description": "Window in days (default: all time)"},
            "limit": {"type": "integer", "default": 25},
        },
        timeout=60.0,
    ),
    "get_market_horizon": ToolSpec(
        name="get_market_horizon",
        description="The Market Maturity Map: each rated vendor's position (momentum vs maturity band), plus which vendors are unrated and why.",
        properties={
            "market": {"type": "string"},
            "market_id": {"type": "integer"},
        },
        timeout=60.0,
    ),
    "get_market_briefings": ToolSpec(
        name="get_market_briefings",
        description="The most recent market briefings (monthly narrative reports) for a market.",
        properties={
            "market": {"type": "string"},
            "market_id": {"type": "integer"},
            "limit": {"type": "integer", "default": 5},
        },
        timeout=30.0,
        max_bytes=_ARTICLE_LIST_BYTES,
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


def _offered(spec: ToolSpec) -> bool:
    if spec.needs_google and not config.google_search_configured():
        return False
    if spec.needs_saas and not config.saas_skills_configured():
        return False
    return True


def available_tools() -> list[ToolSpec]:
    return [t for t in TOOLS.values() if _offered(t)]


def input_schema(spec: ToolSpec) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": dict(spec.properties),
        "required": list(spec.required),
    }


def get_spec(name: str) -> ToolSpec:
    spec = TOOLS.get(name)
    if spec is None or not _offered(spec):
        raise ToolError(f"unknown tool: {name!r}")
    return spec


async def list_capabilities(ctx=None) -> dict[str, Any]:
    from app.database import get_database_instance
    from . import recipes

    topics = await asyncio.to_thread(lambda: get_database_instance().get_topics())
    out = {
        "server": config.server_name(),
        "base_url": config.base_url(),
        "connected_as": getattr(ctx, "username", None),
        "auth_kind": getattr(ctx, "auth_kind", None),
        "topics": list(topics or []),
        "tools": [t.name for t in available_tools()],
        "prompts": [r["name"] for r in recipes.list_recipes()],
        "notes": (
            "Pass a topic name exactly as listed here. Tools that take no topic "
            "search across every topic. Brand and market tools take the names "
            "listed under brands / markets. Before choosing a tool, call "
            "suggest_tool with the user's request: it returns at most one "
            "suggestion with probabilities, or none when no tool is needed. "
            "For 'what has happened with X' or 'anything new on X', prefer "
            "get_timeline and what_changed (the site's own dated memory, with "
            "the articles each event was computed from) over a fresh search."
        ),
    }
    # The brand and market names, so a model can go straight to the brand
    # tools without a list_brands round trip. Absent when the module is off.
    try:
        from sqlalchemy import text as _t
        from app.core.modules import is_module_enabled
        conn = get_database_instance()._temp_get_connection()
        try:
            if is_module_enabled("brand_watcher"):
                out["brands"] = [
                    {"name": r[0], "primary": bool(r[1])} for r in conn.execute(_t(
                        "SELECT display_name, is_primary FROM bw_brands WHERE enabled = true "
                        "ORDER BY is_primary DESC, display_name")).fetchall()]
            if is_module_enabled("market_monitor"):
                out["markets"] = [r[0] for r in conn.execute(_t(
                    "SELECT name FROM bw_markets WHERE enabled = true ORDER BY name")).fetchall()]
        finally:
            conn.close()
    except Exception:  # noqa: BLE001 - the capability list stands without the names
        pass
    return out


_SENTIMENT_WORDS = {
    "positive": ("pos", "optimis"),
    "negative": ("neg", "pessimis", "concern", "critical", "alarm"),
}


def _sentiment_bucket(label: Any) -> str:
    lo = str(label or "").lower()
    if not lo:
        return "unrated"
    if any(w in lo for w in _SENTIMENT_WORDS["positive"]):
        return "positive"
    if any(w in lo for w in _SENTIMENT_WORDS["negative"]):
        return "negative"
    return "neutral"


def _social_posts_sync(brand: str | None, topic: str | None, days_back: int, min_relevance: float,
                       platform: str | None, sentiment: str | None, limit: int,
                       include_owned: bool) -> dict[str, Any]:
    """The Social tab's feed, by brand or topic. Same two read paths as the
    /api/brand-watcher/social route: the entity-mention store when that flag is
    on for the site, the articles table otherwise."""
    import json as _json
    from datetime import datetime, timedelta
    from sqlalchemy import text
    from app.database import get_database_instance
    from app.services import entity_flags
    from app.services.social_sources import SOCIAL_SOURCES

    limit = max(1, min(int(limit or 100), 500))
    days_back = max(1, int(days_back or 7))
    topics_csv = topic or (f"Brand Monitoring {brand}" if brand else None)
    db = get_database_instance()
    conn = db._temp_get_connection()
    try:
        result: dict[str, Any] | None = None
        if entity_flags.mention_read():
            from app.services import entity_social_read as esr
            brand_ids: list[int] = []
            if brand:
                row = conn.execute(text(
                    "SELECT id FROM bw_brands WHERE LOWER(display_name) = LOWER(:n) OR LOWER(name) = LOWER(:n) LIMIT 1"
                ), {"n": brand}).fetchone()
                if row:
                    brand_ids = [int(row[0])]
            if not brand_ids and topics_csv:
                brand_ids = esr.brands_for_topics(conn, topics_csv)
            if brand_ids:
                result = esr.social_feed(
                    conn, brand_ids=brand_ids, days_back=days_back, min_relevance=min_relevance,
                    source=platform, include_unevaluated=False, include_owned=include_owned,
                    include_flagged=False, limit=limit)
        if result is None:
            end = datetime.now()
            start = end - timedelta(days=days_back)
            keys = [platform.lower()] if platform and platform.lower() in ("reddit", "bluesky") else list(SOCIAL_SOURCES)
            if platform and platform.lower() not in ("reddit", "bluesky"):
                keys = [f"xpoz:{platform.lower()}"]
            src = "(" + " OR ".join(f"LOWER(a.news_source) LIKE :s{i}" for i in range(len(keys))) + ")"
            params: dict[str, Any] = {"start": start.strftime("%Y-%m-%d"), "end": end.strftime("%Y-%m-%dT23:59:59"),
                                      "rel": float(min_relevance or 0), "lim": limit}
            for i, k in enumerate(keys):
                params[f"s{i}"] = f"%{k}%"
            topic_clause = ""
            if topics_csv:
                names = [t.strip() for t in topics_csv.split(",") if t.strip()]
                topic_clause = "AND a.topic IN (" + ", ".join(f":t{i}" for i in range(len(names))) + ")"
                for i, n in enumerate(names):
                    params[f"t{i}"] = n
            rows = conn.execute(text(f"""
                SELECT a.uri, a.title, a.summary, a.original_summary, a.news_source, a.publication_date,
                       a.topic_alignment_score, a.sentiment, a.topic, a.social_meta
                FROM articles a
                WHERE a.publication_date >= :start AND a.publication_date <= :end
                  AND {src}
                  AND a.topic_alignment_score >= :rel
                  {topic_clause}
                  AND NOT EXISTS (SELECT 1 FROM bw_finding_reviews r WHERE r.article_uri = a.uri AND r.status = 'false_positive')
                ORDER BY a.publication_date DESC NULLS LAST
                LIMIT :lim
            """), params).fetchall()
            posts = []
            for r in rows:
                meta = r[9] if isinstance(r[9], dict) else (_json.loads(r[9]) if r[9] else {}) or {}
                ns = (r[4] or "").lower()
                plat = ns.split(":", 1)[1] if ns.startswith("xpoz:") else ("bluesky" if "bsky" in ns or "bluesky" in ns else "reddit" if "reddit" in ns else "social")
                posts.append({
                    "uri": r[0], "title": r[1], "summary": r[2], "original_summary": r[3],
                    "platform": plat, "publication_date": str(r[5]) if r[5] else None,
                    "relevance": round(float(r[6]), 3) if r[6] is not None else None,
                    "sentiment": r[7], "topic": r[8],
                    "author": meta.get("author"),
                    "engagement": {k: meta.get(k) for k in ("likes", "reposts", "comments", "plays") if meta.get(k) is not None},
                })
            result = {"window_days": days_back, "min_relevance": min_relevance, "posts": posts}
        posts = list(result.get("posts") or [])
        if sentiment:
            want = sentiment.lower()
            posts = [p for p in posts if _sentiment_bucket(p.get("sentiment")) == want]
        by_platform: dict[str, int] = {}
        by_sentiment: dict[str, int] = {}
        for p in posts:
            by_platform[p.get("platform") or "social"] = by_platform.get(p.get("platform") or "social", 0) + 1
            b = _sentiment_bucket(p.get("sentiment"))
            by_sentiment[b] = by_sentiment.get(b, 0) + 1
        return {
            "brand": brand, "topic": topics_csv, "window_days": days_back, "min_relevance": min_relevance,
            "total": len(posts), "by_platform": by_platform, "by_sentiment": by_sentiment,
            "notes": (
                "summary is the post in English; original_summary is the post as written when it "
                "was not English. Sentiment is the social evaluator's label per post; 'unrated' "
                "posts have not been scored yet."
            ),
            "posts": posts,
        }
    finally:
        conn.close()


async def get_social_posts(ctx=None, brand: str | None = None, topic: str | None = None,
                           days_back: int = 7, min_relevance: float = 0.4,
                           platform: str | None = None, sentiment: str | None = None,
                           limit: int = 100, include_owned: bool = False) -> dict[str, Any]:
    if not brand and not topic:
        raise ToolError("get_social_posts needs a brand or a topic")
    return await asyncio.to_thread(
        _social_posts_sync, brand, topic, days_back, min_relevance, platform, sentiment, limit, include_owned)


from . import brand_tools as _brand_tools  # noqa: E402

_LOCAL_HANDLERS: dict[str, Callable[..., Awaitable[dict[str, Any]]]] = {
    "list_capabilities": list_capabilities,
    "get_social_posts": get_social_posts,
    **_brand_tools.HANDLERS,
}


def resolve(name: str) -> tuple[ToolSpec, Callable[..., Awaitable[dict[str, Any]]]]:
    spec = get_spec(name)
    if spec.method is None:
        fn = _LOCAL_HANDLERS.get(name)
        if fn is not None:
            return spec, fn
        raise ToolError(f"tool {name!r} has no handler")
    from app.services.auspex_tools import get_auspex_tools_service
    fn = getattr(get_auspex_tools_service(), spec.method, None)
    if fn is None:
        raise ToolError(f"tool {name!r} is not available on this site")
    return spec, fn


# ── Typed judgments (TypeSafe Jev) ──────────────────────────────────────────
# Registered last so ToolSpec exists when judgment_tools imports it.
from . import judgment_tools as _judgment_tools  # noqa: E402

TOOLS.update(_judgment_tools.SPECS)
_LOCAL_HANDLERS.update(_judgment_tools.HANDLERS)

# ── Tool-suggestion pre-pass (TypeSafe Jev) ─────────────────────────────────
from . import tool_suggestion as _tool_suggestion  # noqa: E402

TOOLS.update(_tool_suggestion.SPECS)
_LOCAL_HANDLERS.update(_tool_suggestion.HANDLERS)

# ── Timeline mementos: the per-brand / per-topic memory ─────────────────────
from . import timeline_tools as _timeline_tools  # noqa: E402

TOOLS.update(_timeline_tools.SPECS)
_LOCAL_HANDLERS.update(_timeline_tools.HANDLERS)

# ── Trust Signals, rated by the saas Skills API ─────────────────────────────
from . import trust_tools as _trust_tools  # noqa: E402

TOOLS.update(_trust_tools.SPECS)
_LOCAL_HANDLERS.update(_trust_tools.HANDLERS)
