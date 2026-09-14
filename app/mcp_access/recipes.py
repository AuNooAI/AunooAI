"""MCP prompts: named playbooks an assistant can run with this site's tools.
Pure text templates; no database work."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

_CITATION_RULES = (
    "CITATION RULES:\n"
    "- Ground every claim in articles you retrieve with the tools. Cite inline "
    "as markdown links, the article's title as link text and its URL as the "
    "target: [Article Title](https://example.com/article).\n"
    "- Use the exact title and URL the tool returned. Never use bare titles in "
    "brackets, numeric citations like \"[3]\", or footnotes.\n"
    "- Say plainly when the corpus has no coverage of a point. Do not fill the "
    "gap from memory."
)


@dataclass(frozen=True)
class RecipeArg:
    name: str
    description: str
    required: bool = False


@dataclass(frozen=True)
class Recipe:
    name: str
    description: str
    arguments: tuple[RecipeArg, ...]
    render: Callable[[dict[str, Any]], list[dict[str, Any]]]


def _user_message(text: str) -> dict[str, Any]:
    return {"role": "user", "content": [{"type": "text", "text": text}]}


def _topic_clause(args: dict[str, Any]) -> str:
    topic = args.get("topic")
    return f'topic="{topic}"' if topic else "no topic (all topics)"


def _render_topic_briefing(args: dict[str, Any]) -> list[dict[str, Any]]:
    days = args.get("days_back") or 7
    text = f"""You are running Aunoo's **topic briefing** recipe for {_topic_clause(args)} over the last {days} days.

Tool sequence:
1. `list_capabilities` if you have not called it yet, to confirm the topic name.
2. `get_topic_articles` with {_topic_clause(args)}, limit=40, days_back={days}.
3. `analyze_sentiment_trends` with the same topic and time_period="week" (or "month" if days_back > 14).
4. `get_article_categories` with the same topic.

Write a briefing with these sections: what happened (3 to 6 bullets, newest first), what the tone was (use the sentiment percentages, give each number a meaning), what kinds of stories dominated (from the category distribution), and what to watch next week. Keep it under 400 words.

{_CITATION_RULES}"""
    return [_user_message(text)]


def _render_deep_dive(args: dict[str, Any]) -> list[dict[str, Any]]:
    query = args.get("query") or "the user's question"
    text = f"""You are running Aunoo's **deep dive** recipe on: "{query}" ({_topic_clause(args)}).

Tool sequence:
1. `semantic_search_and_analyze` with query="{query}", {_topic_clause(args)}, analysis_type="comprehensive", limit=30.
2. Read the analysis and the articles. Pick the two or three open questions the first pass leaves.
3. For each, call `follow_up_query` with original_query="{query}" and the follow-up as `follow_up`, passing the topic.
4. If a named company, product or person needs confirmation, call `search_articles_by_keywords` with that name.

Write: an opening finding in one or two sentences, evidence grouped by theme, what the sources disagree on, and what remains unknown. Observational, not advice.

{_CITATION_RULES}"""
    return [_user_message(text)]


def _render_keyword_scan(args: dict[str, Any]) -> list[dict[str, Any]]:
    keywords = args.get("keywords") or "the keywords the user gave"
    if isinstance(keywords, list):
        keywords = ", ".join(str(k) for k in keywords)
    text = f"""You are running Aunoo's **keyword scan** recipe for: {keywords} ({_topic_clause(args)}).

Tool sequence:
1. `search_articles_by_keywords` with keywords=[{keywords}], {_topic_clause(args)}, limit=40.
2. Group the hits by which keyword matched and by publication date.
3. For the busiest keyword, call `get_article_categories` on the topic to see whether the coverage is news, analysis or opinion.

Report per keyword: how many articles, the date range, the three most substantive articles, and whether the volume looks like a spike or steady coverage. Say when a keyword returned nothing.

{_CITATION_RULES}"""
    return [_user_message(text)]


def _render_brand_briefing(args: dict[str, Any]) -> list[dict[str, Any]]:
    brand = args.get("brand") or "the primary brand"
    days = args.get("days_back") or 30
    text = f"""You are running Aunoo's **brand briefing** recipe for {brand} over the last {days} days.

Tool sequence:
1. `list_brands`, then `get_brand_stats` with brand="{brand}", days_back={days}: volume, sentiment split, category mix.
2. `get_brand_alerts` with limit=20: anything that fired in the window.
3. `get_brand_voices` with brand="{brand}", days_back={days}: who is talking and what each audience thinks; read the digests for the focus pair (for a health brand, clinicians and patients).
4. `get_brand_articles` with brand="{brand}", days_back={days}, per_page=15, sort_by="relevance" for the news behind the numbers.
5. `get_brand_perception` with days_back={days} to place the brand against its competitors.

Write: the state of the brand in two sentences; what changed in the window; what each audience says, with one quote each; the competitor comparison; what to watch. Give every number its denominator. Observational, not advice.

{_CITATION_RULES}"""
    return [_user_message(text)]


_RECIPES: dict[str, Recipe] = {
    "brand_briefing": Recipe(
        name="brand_briefing",
        description="Brand Watcher briefing for one brand: numbers, alerts, what each audience says, competitors, what to watch.",
        arguments=(
            RecipeArg("brand", "Brand display name from list_brands. Omit for the primary brand."),
            RecipeArg("days_back", "How many days to cover (default 30)."),
        ),
        render=_render_brand_briefing,
    ),
    "topic_briefing": Recipe(
        name="topic_briefing",
        description="Weekly-style briefing for one topic: what happened, tone, story mix, what to watch.",
        arguments=(
            RecipeArg("topic", "Topic name from list_capabilities. Omit for all topics."),
            RecipeArg("days_back", "How many days to cover (default 7)."),
        ),
        render=_render_topic_briefing,
    ),
    "deep_dive": Recipe(
        name="deep_dive",
        description="Research-style synthesis on one question using semantic search and follow-ups.",
        arguments=(
            RecipeArg("query", "The question to research.", required=True),
            RecipeArg("topic", "Topic name from list_capabilities. Omit for all topics."),
        ),
        render=_render_deep_dive,
    ),
    "keyword_scan": Recipe(
        name="keyword_scan",
        description="Volume and substance check for a set of keywords.",
        arguments=(
            RecipeArg("keywords", "Comma-separated keywords.", required=True),
            RecipeArg("topic", "Topic name from list_capabilities. Omit for all topics."),
        ),
        render=_render_keyword_scan,
    ),
}


def list_recipes() -> list[dict[str, Any]]:
    return [
        {
            "name": r.name,
            "description": r.description,
            "arguments": [
                {"name": a.name, "description": a.description, "required": a.required}
                for a in r.arguments
            ],
        }
        for r in _RECIPES.values()
    ]


def get_recipe(name: str) -> Recipe | None:
    return _RECIPES.get(name)


def render_recipe(name: str, arguments: dict[str, Any] | None = None) -> list[dict[str, Any]] | None:
    recipe = _RECIPES.get(name)
    if recipe is None:
        return None
    return recipe.render(dict(arguments or {}))
