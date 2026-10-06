"""MCP tools that expose the timeline mementos: the per-brand and per-topic
memory of what happened, kept current by the scheduler whether or not anyone
is asking.

Three tools, registered into the catalogue by ``tools.py``:

``list_timelines``  every scope that has a timeline (enabled brands and active
    topics), with how many events it holds and the date of the latest one.

``get_timeline``  one scope's memory: the maintained state document (summary,
    trend, key entities), pinned analyst notes, the latest monthly and weekly
    rollups, and the daily events in a window. Every event carries the article
    URIs it was computed from, so the caller can cite or fetch them.

``what_changed``  the same scope read as a diff against a date: events that
    first appeared since then (``new``) and older events that resurfaced in
    the window (``ongoing``, with their occurrence count), plus the rollups
    written in the window. This is the "catch me up" call.

A scope is named the way the other tools name things: ``brand`` (a display
name, as list_brands returns it) or ``topic`` (as list_capabilities returns
it). A "Brand Monitoring <name>" topic resolves to the brand's timeline, which
also carries its risk, alert and story mementos.

All three are read-only and metered like every tool call. They never raise on
data problems; a scope with no timeline yet returns empty lists, so a caller
can tell "nothing happened" from "not tracked" by the ``has_timeline`` flag.
"""
from __future__ import annotations

import asyncio
import json
from datetime import date, datetime, timedelta
from typing import Any, Awaitable, Callable, Optional

from sqlalchemy import text

from .errors import ToolError
from .tools import ToolSpec

MAX_EVENTS = 60
MAX_ARTICLE_LOOKUP = 60
# Answers go back over MCP with a byte cap, so descriptions are trimmed:
# a daily event is a headline with a line of context, a rollup is a paragraph.
DAILY_DESC_CHARS = 400
ROLLUP_DESC_CHARS = 1500
_RESPONSE_BYTES = 192 * 1024

_EVENT_COLS = ("id, event_type, event_subtype, title, description, significance, "
               "entities, article_uris, article_count, event_date, last_seen_date, "
               "occurrence_count, granularity, is_stale, superseded_by_id")


def _conn():
    from app.database import get_database_instance
    return get_database_instance()._temp_get_connection()


def _has_timeline_tables(conn) -> bool:
    return bool(conn.execute(text("SELECT to_regclass('public.timeline_events')")).scalar())


def _iso(v: Any) -> Any:
    if isinstance(v, (date, datetime)):
        return v.isoformat()
    return v


def _json_list(v: Any) -> list:
    if isinstance(v, list):
        return v
    try:
        out = json.loads(v or "[]")
        return out if isinstance(out, list) else []
    except (TypeError, ValueError):
        return []


def _clip(s: Any, n: int) -> Any:
    if not isinstance(s, str) or len(s) <= n:
        return s
    return s[: n - 1].rstrip() + "…"


def _event(r) -> dict[str, Any]:
    gran = r[12]
    desc_chars = DAILY_DESC_CHARS if gran == "daily" else ROLLUP_DESC_CHARS
    return {
        "id": r[0], "event_type": r[1], "event_subtype": r[2], "title": r[3],
        "description": _clip(r[4], desc_chars), "significance": r[5], "entities": _json_list(r[6]),
        "article_uris": _json_list(r[7]), "article_count": r[8],
        "event_date": _iso(r[9]), "last_seen_date": _iso(r[10]),
        "occurrence_count": r[11], "granularity": r[12], "is_stale": bool(r[13]),
        "superseded": r[14] is not None,
    }


def _resolve_scope(conn, brand: Optional[str], brand_id: Optional[int],
                   topic: Optional[str]) -> tuple[str, str, str]:
    """(scope_type, scope_id, label). Brand wins when both are given, because
    the brand timeline also holds the risk and alert mementos."""
    if brand or brand_id is not None:
        from .brand_tools import _brand_row
        bid, name = _brand_row(conn, brand, brand_id)
        return "brand", str(bid), name
    if topic:
        from app.services.timeline_rollup import resolve_scope_for_topic
        from app.services.timeline_events import scope_label
        st, sid = resolve_scope_for_topic(conn, topic.strip())
        if st == "topic":
            exists = conn.execute(text(
                "SELECT 1 FROM keyword_groups WHERE LOWER(topic) = LOWER(:t) LIMIT 1"),
                {"t": sid}).fetchone()
            if not exists:
                raise ToolError(f"topic {topic!r} not found; call list_timelines for the names this site tracks")
            # Keep the stored spelling so the scope_id matches the rows.
            sid = conn.execute(text(
                "SELECT topic FROM keyword_groups WHERE LOWER(topic) = LOWER(:t) LIMIT 1"),
                {"t": sid}).scalar()
        return st, sid, scope_label(conn, st, sid)
    raise ToolError("name a brand or a topic; call list_timelines for what this site keeps a timeline for")


def _since(since: Optional[str], days: Optional[int], default_days: int) -> date:
    if since:
        try:
            return date.fromisoformat(str(since)[:10])
        except ValueError as e:
            raise ToolError(f"since must be an ISO date (YYYY-MM-DD): {e}")
    n = int(days) if days is not None else default_days
    if n < 1 or n > 3650:
        raise ToolError("days must be between 1 and 3650")
    return date.today() - timedelta(days=n)


def _fetch(conn, st: str, sid: str, granularity: str, *, since: Optional[date] = None,
           until: Optional[date] = None, limit: int, on: str = "event_date",
           include_stale: bool = False, exclude_superseded: bool = True) -> list[dict[str, Any]]:
    q = (f"SELECT {_EVENT_COLS} FROM timeline_events WHERE scope_type = :st AND scope_id = :sid "
         "AND granularity = :g")
    p: dict[str, Any] = {"st": st, "sid": sid, "g": granularity}
    if since is not None:
        q += f" AND {on} >= :since"; p["since"] = since
    if until is not None:
        q += f" AND {on} < :until"; p["until"] = until
    if not include_stale:
        q += " AND is_stale = false"
    if exclude_superseded:
        q += " AND superseded_by_id IS NULL"
    q += (" ORDER BY event_date DESC, CASE significance WHEN 'critical' THEN 0 WHEN 'high' THEN 1 "
          f"WHEN 'medium' THEN 2 ELSE 3 END, id DESC LIMIT {int(limit)}")
    return [_event(r) for r in conn.execute(text(q), p).fetchall()]


def _articles_for(conn, events: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Title, source, date and link for the URIs the events cite, most
    significant events first, capped so a long timeline stays a small answer."""
    uris: list[str] = []
    seen: set[str] = set()
    for e in events:
        for u in e.get("article_uris") or []:
            if u not in seen:
                seen.add(u); uris.append(u)
            if len(uris) >= MAX_ARTICLE_LOOKUP:
                break
        if len(uris) >= MAX_ARTICLE_LOOKUP:
            break
    if not uris:
        return {}
    rows = conn.execute(text("""
        SELECT uri, title, news_source, publication_date
        FROM articles WHERE uri = ANY(:uris)
    """), {"uris": uris}).fetchall()
    # The uri is the article's link; nothing else to hand back for it.
    return {r[0]: {"title": r[1], "source": r[2], "published": _iso(r[3])} for r in rows}


def _state(conn, st: str, sid: str) -> Optional[dict[str, Any]]:
    from app.services.timeline_rollup import get_state_doc
    return get_state_doc(conn, st, sid)


def _count(conn, st: str, sid: str) -> tuple[int, Optional[str]]:
    row = conn.execute(text(
        "SELECT COUNT(*), MAX(event_date) FROM timeline_events WHERE scope_type = :st AND scope_id = :sid"),
        {"st": st, "sid": sid}).fetchone()
    return int(row[0] or 0), _iso(row[1])


# ── handlers ────────────────────────────────────────────────────────────────

async def list_timelines(ctx=None) -> dict[str, Any]:
    def _work():
        conn = _conn()
        try:
            if not _has_timeline_tables(conn):
                return {"timelines": [], "note": "this site does not keep timelines"}
            from app.services.timeline_events import get_timeline_scopes
            scopes = get_timeline_scopes(conn)
            counts = {(r[0], r[1]): (int(r[2]), _iso(r[3]), _iso(r[4])) for r in conn.execute(text("""
                SELECT scope_type, scope_id, COUNT(*), MAX(event_date), MAX(last_seen_date)
                FROM timeline_events GROUP BY scope_type, scope_id""")).fetchall()}
            docs = {(r[0], r[1]): _iso(r[2]) for r in conn.execute(text(
                "SELECT scope_type, scope_id, generated_at FROM timeline_state_docs")).fetchall()}
            out = []
            for s in scopes:
                key = (s["scope_type"], s["scope_id"])
                n, latest, seen = counts.get(key, (0, None, None))
                out.append({
                    "kind": s["scope_type"], "name": s["label"],
                    "event_count": n, "latest_event_date": latest, "last_seen_date": seen,
                    "state_doc_generated_at": docs.get(key),
                    "has_timeline": n > 0,
                })
            out.sort(key=lambda x: (not x["has_timeline"], -(x["event_count"])))
            return {"timelines": out,
                    "note": ("Pass a brand name as `brand` or a topic name as `topic` to "
                             "get_timeline or what_changed.")}
        finally:
            conn.close()
    return await asyncio.to_thread(_work)


async def get_timeline(ctx=None, brand: str | None = None, brand_id: int | None = None,
                       topic: str | None = None, days: int | None = None,
                       since: str | None = None, limit: int = 30,
                       include_articles: bool = False) -> dict[str, Any]:
    lim = max(1, min(int(limit or 30), MAX_EVENTS))
    start = _since(since, days, default_days=90)

    def _work():
        conn = _conn()
        try:
            if not _has_timeline_tables(conn):
                raise ToolError("this site does not keep timelines")
            st, sid, label = _resolve_scope(conn, brand, brand_id, topic)
            total, latest = _count(conn, st, sid)
            out: dict[str, Any] = {
                "scope": {"kind": st, "name": label},
                "has_timeline": total > 0, "event_count": total, "latest_event_date": latest,
                "window": {"since": start.isoformat(), "until": date.today().isoformat()},
                "state": _state(conn, st, sid),
                "analyst_notes": _fetch(conn, st, sid, "permanent", limit=10,
                                        include_stale=True, exclude_superseded=False),
                "monthly": _fetch(conn, st, sid, "monthly", since=start, limit=3,
                                  exclude_superseded=False),
                "weekly": _fetch(conn, st, sid, "weekly", since=start, limit=8,
                                 exclude_superseded=False),
                "events": _fetch(conn, st, sid, "daily", since=start, limit=lim),
            }
            out["limit_reached"] = len(out["events"]) >= lim
            if include_articles:
                out["articles"] = _articles_for(conn, out["events"] + out["weekly"])
            out["note"] = ("Events are ordered newest first, most significant first within a day. "
                           "occurrence_count > 1 means the same story resurfaced; article_uris are "
                           "the evidence, fetch any with get_article_full.")
            return out
        finally:
            conn.close()
    return await asyncio.to_thread(_work)


async def what_changed(ctx=None, brand: str | None = None, brand_id: int | None = None,
                       topic: str | None = None, since: str | None = None,
                       days: int | None = None, limit: int = 40,
                       include_articles: bool = False) -> dict[str, Any]:
    lim = max(1, min(int(limit or 40), MAX_EVENTS))
    start = _since(since, days, default_days=7)

    def _work():
        conn = _conn()
        try:
            if not _has_timeline_tables(conn):
                raise ToolError("this site does not keep timelines")
            st, sid, label = _resolve_scope(conn, brand, brand_id, topic)
            total, latest = _count(conn, st, sid)
            # New: first seen in the window. Ongoing: first seen before the
            # window, but bumped inside it. Both exclude superseded dailies,
            # because their rollup says the same thing once.
            new = _fetch(conn, st, sid, "daily", since=start, limit=lim)
            bumped = _fetch(conn, st, sid, "daily", since=start, limit=lim, on="last_seen_date")
            new_ids = {e["id"] for e in new}
            ongoing = [e for e in bumped if e["id"] not in new_ids]
            state = _state(conn, st, sid)
            out: dict[str, Any] = {
                "scope": {"kind": st, "name": label},
                "has_timeline": total > 0, "latest_event_date": latest,
                "window": {"since": start.isoformat(), "until": date.today().isoformat()},
                "trend": (state or {}).get("current_trend"),
                "state_summary": (state or {}).get("summary"),
                "new": new,
                "ongoing": ongoing,
                "rollups": (_fetch(conn, st, sid, "monthly", since=start, limit=2, exclude_superseded=False)
                            + _fetch(conn, st, sid, "weekly", since=start, limit=4, exclude_superseded=False)),
                "counts": {"new": len(new), "ongoing": len(ongoing)},
                "limit_reached": len(new) >= lim or len(bumped) >= lim,
            }
            if include_articles:
                out["articles"] = _articles_for(conn, new + ongoing)
            if total and not new and not ongoing:
                out["note"] = "Nothing new in the window. The timeline exists; see latest_event_date."
            elif not total:
                out["note"] = "No timeline yet for this scope; it fills in after the first daily run."
            return out
        finally:
            conn.close()
    return await asyncio.to_thread(_work)


# ── catalogue ───────────────────────────────────────────────────────────────

_BRAND = {"type": "string", "description": "Brand display name, as list_brands or list_timelines returns it."}
_BRAND_ID = {"type": "integer", "description": "Brand id, if known. Alternative to brand."}
_TOPIC = {"type": "string", "description": "Topic name, as list_capabilities or list_timelines returns it."}
_SINCE = {"type": "string", "description": "ISO date (YYYY-MM-DD). Overrides days."}
_ARTICLES = {"type": "boolean", "default": False,
             "description": "Also return title, source, date and link for the articles the events cite (capped at 60)."}

SPECS: dict[str, ToolSpec] = {
    "list_timelines": ToolSpec(
        name="list_timelines",
        description=(
            "The brands and topics this site keeps a timeline (memory) for, with how many "
            "events each holds and when the latest was. Call before get_timeline or "
            "what_changed when you do not know the exact name."
        ),
        properties={},
        timeout=20.0,
    ),
    "get_timeline": ToolSpec(
        name="get_timeline",
        description=(
            "A brand's or topic's memory: the maintained state summary and trend, pinned "
            "analyst notes, the latest monthly and weekly rollups, and the dated events in "
            "a window (default 90 days), newest first. Each event cites the article URIs it "
            "was computed from. Use this to answer 'what has happened with X' from the site's "
            "own record instead of a fresh search."
        ),
        properties={
            "brand": _BRAND, "brand_id": _BRAND_ID, "topic": _TOPIC,
            "days": {"type": "integer", "description": "Window length in days (default 90).", "default": 90},
            "since": _SINCE,
            "limit": {"type": "integer", "description": f"Max daily events (default 30, max {MAX_EVENTS}).", "default": 30},
            "include_articles": _ARTICLES,
        },
        timeout=30.0,
        max_bytes=_RESPONSE_BYTES,
    ),
    "what_changed": ToolSpec(
        name="what_changed",
        description=(
            "Catch up on a brand or topic since a date (default the last 7 days): events that "
            "first appeared in the window ('new') and older events that resurfaced in it "
            "('ongoing', with how often they have been seen), plus any weekly or monthly "
            "rollup written in the window and the current trend. Use this for 'anything new "
            "on X?' and for distinguishing a new development from a story that keeps coming back."
        ),
        properties={
            "brand": _BRAND, "brand_id": _BRAND_ID, "topic": _TOPIC,
            "since": _SINCE,
            "days": {"type": "integer", "description": "Window length in days (default 7).", "default": 7},
            "limit": {"type": "integer", "description": f"Max events per list (default 40, max {MAX_EVENTS}).", "default": 40},
            "include_articles": _ARTICLES,
        },
        timeout=30.0,
        max_bytes=_RESPONSE_BYTES,
    ),
}

HANDLERS: dict[str, Callable[..., Awaitable[dict[str, Any]]]] = {
    "list_timelines": list_timelines,
    "get_timeline": get_timeline,
    "what_changed": what_changed,
}
