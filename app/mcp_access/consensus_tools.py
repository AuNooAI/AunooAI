"""MCP tool that returns a topic's saved consensus analysis.

The consensus analysis is the Explore page's Consensus tab: an LLM reads a
topic's recent articles and groups them into categories, each with how far
sources agree, when they expect it to happen, the outliers on either side,
and the key articles. Every run is saved in ``analysis_versions``, one row
per run, holding only the tab that run produced.

``get_consensus`` reads the newest saved run that has consensus categories,
the same row the Consensus tab shows (``/api/trend-convergence/{topic}/previous
?tab=consensus``). It never starts a new analysis, so a call costs no model
spend. A topic with no saved run returns ``has_consensus: false`` and the
topics that do have one, rather than an error.

Category text cites articles as ``[n]``; ``n`` is the ``id`` in the returned
``article_list``.
"""
from __future__ import annotations

import asyncio
import json
from datetime import datetime
from typing import Any, Awaitable, Callable

from sqlalchemy import text

from .tools import ToolSpec

#: How many recent runs to scan for one that carries consensus categories.
#: A later run of another tab (horizons, signals) saves a row without them.
SCAN_LIMIT = 20
#: Older than this, the answer says so, so the assistant can flag it.
STALE_DAYS = 14
_RESPONSE_BYTES = 192 * 1024

#: How to lay the answer out, returned with the data because many clients
#: never show the consensus_outliers prompt to the assistant.
DISPLAY = (
    "To SHOW consensus (not just describe it): one card per category, leading with the "
    "cards. Each card: the name; a horizontal stacked bar from consensus_type.distribution "
    "(positive #16a34a, neutral #94a3b8, critical #dc2626, summing to 100); "
    "confidence.majority_agreement as a percent with confidence.consensus_strength; "
    "timeline.consensus_window.label; and an outliers row, a green up-triangle per "
    "optimistic_outliers item and a red down-triangle per pessimistic_outliers item, each "
    "with its scenario and year. Then a Key insights list. Above the cards a stat row: "
    "themes (number of categories), articles_analyzed, and the most common consensus_window "
    "end year. Inter font, light cards (bg #faf9fb, border #dbd8e0), pink #d6409f accents, "
    "text #211f26. Use the categories and numbers as given; never add, rename or re-round "
    "one. Always include the outliers. A standalone HTML file must be self-contained: "
    "inline CSS and SVG, no ES modules, no fetch."
)

#: The stored category keys carry a number for display order; the tool
#: returns plain names.
_CATEGORY_KEYS = {
    "category_name": "name",
    "category_description": "description",
    "articles_analyzed": "articles_analyzed",
    "1_consensus_type": "consensus_type",
    "2_timeline_consensus": "timeline",
    "3_confidence_level": "confidence",
    "4_optimistic_outliers": "optimistic_outliers",
    "5_pessimistic_outliers": "pessimistic_outliers",
    "6_key_articles": "key_articles",
    "7_strategic_implications": "strategic_implications",
    "8_key_decision_windows": "decision_windows",
    "9_timeframe_analysis": "timeframe_analysis",
}


def _conn():
    from app.database import get_database_instance
    return get_database_instance()._temp_get_connection()


def _has_categories(payload: dict[str, Any]) -> bool:
    cats = payload.get("categories")
    return isinstance(cats, list) and len(cats) > 0


def _category(c: dict[str, Any]) -> dict[str, Any]:
    out = {plain: c[stored] for stored, plain in _CATEGORY_KEYS.items() if stored in c}
    # Keep anything a newer prompt adds, under its stored name.
    out.update({k: v for k, v in c.items() if k not in _CATEGORY_KEYS})
    return out


def _topics_with_consensus(conn) -> list[dict[str, Any]]:
    rows = conn.execute(text("""
        SELECT topic, MAX(created_at) FROM analysis_versions
        WHERE version_data LIKE '%"category_name"%' AND topic <> '__all__'
        GROUP BY topic ORDER BY MAX(created_at) DESC""")).fetchall()
    return [{"topic": r[0], "latest_run": r[1].isoformat() if r[1] else None} for r in rows]


def _latest(conn, topic: str) -> tuple[str, dict[str, Any], datetime | None] | None:
    # Exact name first, then a case-insensitive match for a loosely typed topic.
    for clause in ("topic = :t", "LOWER(topic) = LOWER(:t)"):
        rows = conn.execute(text(f"""
            SELECT topic, version_data, created_at FROM analysis_versions
            WHERE {clause} ORDER BY created_at DESC LIMIT :n"""),
            {"t": topic, "n": SCAN_LIMIT}).fetchall()
        for r in rows:
            try:
                payload = json.loads(r[1])
            except Exception:  # noqa: BLE001 - a bad row is skipped, not fatal
                continue
            if isinstance(payload, dict) and _has_categories(payload):
                return r[0], payload, r[2]
        if rows:
            return None
    return None


def _get_consensus_sync(topic: str, include_articles: bool) -> dict[str, Any]:
    conn = _conn()
    try:
        found = _latest(conn, topic)
        if found is None:
            return {
                "topic": topic, "has_consensus": False,
                "topics_with_consensus": _topics_with_consensus(conn),
                "note": ("No saved consensus analysis for this topic. One is made by running "
                         "the Consensus tab on the site's Explore page; this tool only reads "
                         "saved runs."),
            }
        name, p, created = found
    finally:
        conn.close()

    generated = p.get("generated_at") or (created.isoformat() if created else None)
    age_days = None
    try:
        age_days = (datetime.now() - datetime.fromisoformat(str(generated))).days
    except (TypeError, ValueError):
        pass
    profile = p.get("organizational_profile")
    out: dict[str, Any] = {
        "topic": name,
        "has_consensus": True,
        "generated_at": generated,
        "age_days": age_days,
        "articles_analyzed": p.get("articles_analyzed"),
        "timeframe_days": p.get("timeframe_days"),
        "model_used": p.get("model_used"),
        "written_for": profile.get("name") if isinstance(profile, dict) else None,
        "categories": [_category(c) for c in p["categories"] if isinstance(c, dict)],
        "key_insights": p.get("key_insights") or [],
        "notes": (
            "Each category is one area the sources discuss. consensus_type.distribution is the "
            "share of sources that are positive, neutral or critical; confidence.majority_agreement "
            "is the share that agree on the category's main claim. Text cites articles as [n]; "
            "n is the id in article_list."
        ),
        "display": DISPLAY,
    }
    if age_days is not None and age_days > STALE_DAYS:
        out["stale"] = (f"This analysis is {age_days} days old. Say so when you use it; a fresh "
                        "one needs a run of the Consensus tab on the site.")
    if include_articles:
        out["article_list"] = p.get("article_list") or []
    return out


async def get_consensus(ctx=None, topic: str | None = None,
                        include_articles: bool = True) -> dict[str, Any]:
    if not topic:
        def _list():
            conn = _conn()
            try:
                return _topics_with_consensus(conn)
            finally:
                conn.close()
        return {"has_consensus": False, "topics_with_consensus": await asyncio.to_thread(_list),
                "note": "Pass one of these as `topic` to get its consensus analysis."}
    return await asyncio.to_thread(_get_consensus_sync, topic, bool(include_articles))


SPECS: dict[str, ToolSpec] = {
    "get_consensus": ToolSpec(
        name="get_consensus",
        description=(
            "A topic's saved consensus analysis: where sources agree and disagree. Returns "
            "categories, each with the share of sources positive, neutral or critical, how "
            "strongly they agree, the expected timeframe, optimistic and pessimistic outliers, "
            "key articles and strategic implications, plus the article list the text cites. "
            "Reads the newest saved run (no new analysis is started); check age_days. The "
            "answer carries `display`, how to show it. Omit topic to list the topics that "
            "have one."
        ),
        properties={
            "topic": {"type": "string",
                      "description": "Topic name as listed by list_capabilities. Omit to list topics with a saved consensus."},
            "include_articles": {"type": "boolean",
                                 "description": "Include article_list, which the [n] citations refer to (default true).",
                                 "default": True},
        },
        timeout=30.0,
        max_bytes=_RESPONSE_BYTES,
    ),
}

HANDLERS: dict[str, Callable[..., Awaitable[dict[str, Any]]]] = {
    "get_consensus": get_consensus,
}
