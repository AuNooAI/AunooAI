"""MCP tools for a topic's saved Future Horizons analysis.

Future Horizons is the Explore page's Horizons tab: an LLM sorts a topic's
recent coverage into scenarios on three horizons (h1 Current, h2 Transition,
h3 Future), each with a title, a year range and a sentiment. Every run is
saved in ``analysis_versions``, one row per run, holding only the tab that
run produced.

``get_horizons`` reads the newest saved run whose ``scenarios`` list holds
horizon scenarios, the same row the Horizons tab shows
(``/api/trend-convergence/{topic}/previous?tab=horizons``).
``render_horizons_chart`` draws that run as the S-curve SVG saas returns, with
every scenario on its curve. Neither starts a new analysis, so a call costs no
model spend.
"""
from __future__ import annotations

import asyncio
import json
import re
from datetime import datetime
from typing import Any, Awaitable, Callable

from sqlalchemy import text

from .tools import ToolSpec

#: How many recent runs to scan for one that carries horizon scenarios.
SCAN_LIMIT = 20
#: Older than this, the answer says so, so the assistant can flag it.
STALE_DAYS = 14
_BANDS = ("h1", "h2", "h3")
_BAND_NAMES = {"h1": "Current", "h2": "Transition", "h3": "Future"}
_YEAR = re.compile(r"(?<!\d)(19\d\d|2[01]\d\d)(?!\d)")

#: How to lay the answer out, returned with the data because many clients
#: never show the future_horizons prompt to the assistant.
DISPLAY = (
    "To SHOW horizons (not just describe them): lead with the S-curve. Call "
    "render_horizons_chart with the same topic and paste its image_svg VERBATIM "
    "into the artifact, wrapped in a div at width:100%; never hand-draw bare curves "
    "and never paste a base64 PNG. Beneath it, three columns: H1 Current (declining, "
    "#d6409f), H2 Transition (#8e4ec6), H3 Future (#0090ff), each listing its "
    "scenarios as 'title, start to end, sentiment'. Inter font, light cards (bg "
    "#faf9fb, border #dbd8e0), text #211f26. Use the scenarios as given; never invent "
    "one. A standalone HTML file must be self-contained: inline CSS and SVG, no ES "
    "modules, no fetch."
)


def _conn():
    from app.database import get_database_instance
    return get_database_instance()._temp_get_connection()


def _years(timeframe: Any) -> tuple[int | None, int | None]:
    found = [int(y) for y in _YEAR.findall(str(timeframe or ""))]
    if not found:
        return None, None
    return min(found), max(found)


def _scenarios(payload: dict[str, Any]) -> list[dict[str, Any]]:
    out = []
    for s in payload.get("scenarios") or []:
        if not isinstance(s, dict):
            continue
        band = str(s.get("type") or "").lower()
        if band not in _BANDS:
            continue
        start, end = _years(s.get("timeframe"))
        out.append({
            "type": band,
            "horizon": _BAND_NAMES[band],
            "title": s.get("title"),
            "description": s.get("description"),
            "timeframe": s.get("timeframe"),
            "timeline_start": start,
            "timeline_end": end,
            "sentiment": s.get("sentiment"),
        })
    return out


def _payload(raw: str) -> dict[str, Any] | None:
    try:
        payload = json.loads(raw)
    except Exception:  # noqa: BLE001 - a bad row is skipped, not fatal
        return None
    return payload if isinstance(payload, dict) and _scenarios(payload) else None


def _topics_with_horizons(conn) -> list[dict[str, Any]]:
    # The LIKE also matches keys such as disruption_scenarios, so each row is parsed.
    rows = conn.execute(text("""
        SELECT topic, version_data, created_at FROM analysis_versions
        WHERE version_data LIKE '%"scenarios": [{%' AND topic <> '__all__'
        ORDER BY created_at DESC""")).fetchall()
    seen: dict[str, str | None] = {}
    for r in rows:
        if r[0] in seen or _payload(r[1]) is None:
            continue
        seen[r[0]] = r[2].isoformat() if r[2] else None
    return [{"topic": t, "latest_run": at} for t, at in seen.items()]


def _latest(conn, topic: str) -> tuple[str, dict[str, Any], datetime | None] | None:
    # Exact name first, then a case-insensitive match for a loosely typed topic.
    for clause in ("topic = :t", "LOWER(topic) = LOWER(:t)"):
        rows = conn.execute(text(f"""
            SELECT topic, version_data, created_at FROM analysis_versions
            WHERE {clause} ORDER BY created_at DESC LIMIT :n"""),
            {"t": topic, "n": SCAN_LIMIT}).fetchall()
        for r in rows:
            payload = _payload(r[1])
            if payload is not None:
                return r[0], payload, r[2]
        if rows:
            return None
    return None


def _missing(conn, topic: str | None) -> dict[str, Any]:
    out: dict[str, Any] = {"has_horizons": False, "topics_with_horizons": _topics_with_horizons(conn)}
    if topic:
        out["topic"] = topic
        out["note"] = ("No saved Future Horizons analysis for this topic. One is made by running "
                       "the Horizons tab on the site's Explore page; this tool only reads saved runs.")
    else:
        out["note"] = "Pass one of these as `topic`."
    return out


def _horizons_sync(topic: str | None) -> dict[str, Any]:
    conn = _conn()
    try:
        found = _latest(conn, topic) if topic else None
        if found is None:
            return _missing(conn, topic)
    finally:
        conn.close()
    name, p, created = found
    generated = p.get("generated_at") or (created.isoformat() if created else None)
    age_days = None
    try:
        age_days = (datetime.now() - datetime.fromisoformat(str(generated))).days
    except (TypeError, ValueError):
        pass
    scenarios = _scenarios(p)
    profile = p.get("organizational_profile")
    out: dict[str, Any] = {
        "topic": name,
        "has_horizons": True,
        "generated_at": generated,
        "age_days": age_days,
        "articles_analyzed": p.get("articles_analyzed"),
        "timeframe_days": p.get("timeframe_days"),
        "model_used": p.get("model_used"),
        "written_for": profile.get("name") if isinstance(profile, dict) else None,
        "counts": {b: sum(1 for s in scenarios if s["type"] == b) for b in _BANDS},
        "scenarios": scenarios,
        "display": DISPLAY,
    }
    if age_days is not None and age_days > STALE_DAYS:
        out["stale"] = (f"This analysis is {age_days} days old. Say so when you use it; a fresh "
                        "one needs a run of the Horizons tab on the site.")
    return out


async def get_horizons(ctx=None, topic: str | None = None) -> dict[str, Any]:
    return await asyncio.to_thread(_horizons_sync, topic)


async def render_horizons_chart(ctx=None, topic: str | None = None) -> dict[str, Any]:
    data = await get_horizons(ctx, topic=topic)
    if not data.get("has_horizons"):
        return data
    from .horizons_svg import render_horizons_svg
    svg = render_horizons_svg({"topic_label": data["topic"], "scenarios": data["scenarios"]})
    return {
        "topic": data["topic"],
        "generated_at": data["generated_at"],
        "age_days": data["age_days"],
        "counts": data["counts"],
        "note": ("image_svg is a self-contained SVG of the Three-Horizons chart with every "
                 "scenario plotted on its curve. Paste it VERBATIM into your HTML/JSX artifact "
                 "(it scales to width:100%). Do not hand-draw the curve. Call get_horizons for "
                 "the scenario text."),
        **({"stale": data["stale"]} if data.get("stale") else {}),
        "image_svg": svg,
    }


_TOPIC = {"type": "string",
          "description": "Topic name as listed by list_capabilities. Omit to list topics with a saved Future Horizons analysis."}

SPECS: dict[str, ToolSpec] = {
    "get_horizons": ToolSpec(
        name="get_horizons",
        description=(
            "A topic's saved Future Horizons analysis: scenarios on three horizons (h1 Current, "
            "h2 Transition, h3 Future), each with a title, description, year range and sentiment. "
            "Reads the newest saved run (no new analysis is started); check age_days. The answer "
            "carries `display`, how to show it; pair it with render_horizons_chart. Omit topic "
            "to list the topics that have one."
        ),
        properties={"topic": _TOPIC},
        timeout=30.0,
    ),
    "render_horizons_chart": ToolSpec(
        name="render_horizons_chart",
        description=(
            "The Three-Horizons S-curve chart for a topic's saved Future Horizons analysis, as a "
            "self-contained SVG (image_svg, about 8 KB) with every scenario plotted on its curve. "
            "Paste it verbatim into a report or artifact. Omit topic to list the topics that "
            "have one."
        ),
        properties={"topic": _TOPIC},
        timeout=30.0,
    ),
}

HANDLERS: dict[str, Callable[..., Awaitable[dict[str, Any]]]] = {
    "get_horizons": get_horizons,
    "render_horizons_chart": render_horizons_chart,
}
