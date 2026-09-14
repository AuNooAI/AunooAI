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


_VOICES_HTML_SKELETON = """<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>Voices — BRAND</title>
<style>
:root{--accent:#D6409F;--live:#16a34a;--neg:#dc2626;--bg:#ECEDF3;--card:#fff;--border:#e0e1e9;--text:#1a1a2e;--text2:#3d3a4a;--muted:#65636d;--r:12px}
*{box-sizing:border-box}body{margin:0;font-family:Inter,-apple-system,'Segoe UI',Roboto,sans-serif;background:var(--bg);color:var(--text);font-size:14px;line-height:1.55}
main{max-width:1100px;margin:0 auto;padding:22px 20px 60px}h1{font-size:22px;margin:6px 0 2px}.lead{color:var(--muted);margin:0 0 18px}
section{margin:26px 0}section>h2{font-size:13px;text-transform:uppercase;letter-spacing:.06em;color:var(--accent);margin:0 0 12px}
.card{background:var(--card);border:1px solid var(--border);border-radius:var(--r);padding:16px 18px;margin-bottom:14px}
.two-col{display:grid;grid-template-columns:1fr 1fr;gap:14px;align-items:start}
table{width:100%;border-collapse:collapse;font-size:13px}th{font-size:10.5px;text-transform:uppercase;color:var(--muted);text-align:left;padding:6px 8px;border-bottom:1px solid var(--border)}
td{padding:8px;border-bottom:1px solid #f0f0f4}td.num{text-align:right}
.chip{font-size:10.5px;padding:1px 7px;border-radius:999px;font-weight:600;background:#fdf3d0;color:#92400e}.chip.pos{background:#e7f6ec;color:#15803d}.chip.neg{background:#fdeaea;color:#b91c1c}
.ctx{font-size:12.5px;color:var(--muted)}.summary{font-size:14px}.theme{border:1px solid #f0f0f4;border-radius:8px;padding:8px 10px;margin-bottom:8px}
.quotes{list-style:none;padding:0;margin:6px 0 0}.quotes li{font-size:12.5px;color:var(--text2);border-left:2px solid #e5e7eb;padding-left:8px;margin:4px 0;font-style:italic}
.post{border-bottom:1px solid #f0f0f4;padding:9px 0 9px 10px;border-left:3px solid transparent}.post.pos{border-left-color:var(--live)}.post.neg{border-left-color:var(--neg)}
.post-head{display:flex;gap:8px;font-size:11px;color:var(--muted)}.post-body{font-size:13px;color:var(--text2);white-space:pre-wrap}.why{font-size:11px;color:var(--muted);font-style:italic}
footer{margin-top:40px;padding-top:16px;border-top:1px solid var(--border);color:var(--muted);font-size:11.5px;text-align:center}
@media(max-width:760px){.two-col{grid-template-columns:1fr}}
</style></head><body><main>
<h1>BRAND — who is talking, and what each audience says</h1>
<p class="lead">Last N days · on-brand social and community posts (relevance ≥ 0.4) · the brand's own accounts are listed as brand voice and never counted in an audience's sentiment.</p>
<section id="overview"><h2>Overview</h2>…stat cards: posts about the brand, audiences heard, net sentiment per compared audience…</section>
<section id="audiences"><h2>Audiences</h2><div class="card"><table>…one row per role: label, posts, +, ·, −, net chip, platforms…</table></div></section>
<section id="compare"><h2>Side by side</h2><div class="two-col">
  <div class="card"><h3>AUDIENCE A · n posts · net</h3><p class="ctx">digest.context</p><p class="summary">digest.summary</p>
    <div class="theme">theme · sentiment chip · post_count<ul class="quotes"><li>“verbatim quote”</li></ul></div>
    <h4>What these posts ask for</h4><ul>…digest.asks…</ul>
    <h4>Posts</h4><div class="post pos|neu|neg"><div class="post-head">platform · @author · date · sentiment · <a href=uri>view</a></div><div class="post-body">text</div><div class="why">role source</div></div></div>
  <div class="card">…AUDIENCE B, same shape…</div>
</div></section>
<section id="method"><h2>Method</h2><div class="card">…three paragraphs, see the recipe…</div></section>
<footer>Generated DATE · Powered by AunooAI · Voices report</footer></main></body></html>"""


def _render_voices_report(args: dict[str, Any]) -> list[dict[str, Any]]:
    brand = args.get("brand") or "the primary brand"
    days = args.get("days_back") or 90
    roles = args.get("roles")
    roles_clause = f'roles="{roles}"' if roles else "no roles argument (the focus pair)"
    text = f"""You are running Aunoo's **voices report** recipe for {brand} over the last {days} days. The output is ONE self-contained HTML file, the same report the Voices tab exports, built from the data the tools return. Nothing in it may come from memory.

Tool sequence:
1. `get_brand_voices` with brand="{brand}", days_back={days}, with_digest=true, {roles_clause}, posts_per_role=60. Everything you need is in that one response: `roles` (ranked, each with n / positive / neutral / negative / net / by_platform / posts), `focus` (the two audiences to put side by side unless roles were given), `digests` keyed by role (context, summary, themes with quotes, asks, tone_warning), and `coverage_notes`.
2. Nothing else. Do not call other tools, do not search, do not add posts or quotes that are not in the response.

Render this structure, in this order, using the skeleton and CSS below (keep the colours and class names; fill the parts marked …):
- Header: "<brand> — who is talking, and what each audience says", then the lead line with the window and the relevance floor.
- Overview: stat cards for posts about the brand (and how many are from outside voices, i.e. not the brand role), audiences heard, and the net sentiment of each compared audience over its post count. If `coverage_notes` is non-empty, list them in a card.
- Audiences: one table row per role in the order returned: label, posts, positive, neutral, negative, net (chip: pos ≥ +20, neg ≤ −20), platforms with counts. Under the table: "Net sentiment = (positive − negative) ÷ posts × 100. Small counts move it a long way; read the number with the count beside it."
- Side by side: one card per compared audience. In each: the digest's context line, its summary, each theme with its sentiment chip, post count and verbatim quotes, then "What these posts ask for" from `asks`, then every post with platform, @author, date, sentiment, a link to `uri`, the text, and one line saying where the role came from (`author_role_source`: post → "Why this role: <author_role_reason>"; account_profile → "Role from the account profile"; account_posts → "Role from this account's other posts"; add "; this post alone read as <post_role>" when it differs). If `tone_warning` is set, show it above the themes.
- Method: three short paragraphs — how each post gets a relevance, a sentiment and a role (patient, caregiver, clinician, customer, academic, professional, employee, journalist, investor, brand, unknown); that the account outranks the single post (profile role first, else the majority of the account's other classified posts); that the digest attributes and counts, gives context, quotes verbatim, lists what the posts ask for, and passes no verdict on the brand or the audience.
- Footer: "Generated <date> · Powered by AunooAI · Voices report".

Rules:
- Every number, quote, post and ask comes from the tool response. Quotes stay verbatim, original language kept. HTML-escape all text.
- Write nothing in your own voice that judges the brand or the audience; the digest text is the analysis. If you must add a sentence, attribute it to the posts and count it.
- Name the file voices-<brand-slug>-<YYYY-MM-DD>.html. Return the complete HTML in one code block, or save it as a file when your client can.

SKELETON:
{_VOICES_HTML_SKELETON}"""
    return [_user_message(text)]


_RECIPES: dict[str, Recipe] = {
    "voices_report": Recipe(
        name="voices_report",
        description="Render the Voices view (who is talking about a brand, and what each audience says) as the same self-contained HTML report the tab exports, from get_brand_voices alone.",
        arguments=(
            RecipeArg("brand", "Brand display name from list_brands. Omit for the primary brand."),
            RecipeArg("days_back", "Window in days (default 90)."),
            RecipeArg("roles", "Comma-separated roles to put side by side (default: the focus pair, e.g. clinician,patient)."),
        ),
        render=_render_voices_report,
    ),
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
