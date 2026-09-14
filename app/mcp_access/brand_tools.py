"""Brand Watcher and Market Monitor over MCP.

The catalogue in ``tools.py`` grew out of the topic tools, so a connected
model could read articles and social posts but not the brand and market
views the site itself shows: category counts, perception, who is talking
and what each audience thinks, alerts, market vendors, the Maturity Map,
top voices, briefings. These handlers expose those views by calling the
same route functions and services the UI calls, so a number here is the
number on screen.

Every route parameter is passed explicitly: FastAPI ``Query(...)`` defaults
are descriptor objects when a route function is called directly, not values.
Results go through ``_plain`` so rows, dates and Decimals serialise.
"""

from __future__ import annotations

import asyncio
import json
import os
from typing import Any, Optional

from sqlalchemy import text

from .errors import ToolError


def _plain(obj: Any) -> Any:
    """JSON-safe copy: pydantic response models, SQLAlchemy rows, dates, Decimals."""
    def enc(o: Any) -> Any:
        if hasattr(o, "model_dump"):
            return o.model_dump()
        if hasattr(o, "_mapping"):
            return dict(o._mapping)
        if hasattr(o, "dict") and callable(o.dict) and not isinstance(o, dict):
            return o.dict()
        return str(o)
    return json.loads(json.dumps(obj, default=enc, ensure_ascii=False))


def _module_on(module_id: str) -> None:
    from app.core.modules import is_module_enabled
    if not is_module_enabled(module_id):
        raise ToolError(f"{module_id} is not enabled on this site")


def _conn():
    from app.database import get_database_instance
    return get_database_instance()._temp_get_connection()


def _brand_row(conn, brand: Optional[str], brand_id: Optional[int]) -> tuple[int, str]:
    """(id, display_name) from a name or an id; the primary brand when neither is given."""
    if brand_id is not None:
        row = conn.execute(text("SELECT id, display_name FROM bw_brands WHERE id = :b"),
                           {"b": int(brand_id)}).fetchone()
    elif brand:
        name = brand.strip()
        for prefix in ("Brand Monitoring ", "Market Monitoring "):
            if name.startswith(prefix):
                name = name[len(prefix):]
        row = conn.execute(text("""
            SELECT id, display_name FROM bw_brands
             WHERE LOWER(display_name) = LOWER(:n) OR LOWER(name) = LOWER(:n)
             ORDER BY enabled DESC, is_primary DESC LIMIT 1"""), {"n": name}).fetchone()
    else:
        row = conn.execute(text("""
            SELECT id, display_name FROM bw_brands WHERE enabled = true
             ORDER BY is_primary DESC, display_name LIMIT 1""")).fetchone()
    if not row:
        raise ToolError("brand not found; call list_brands for the names this site tracks")
    return int(row[0]), row[1]


def _market_id(conn, market: Optional[str], market_id: Optional[int]) -> int:
    if market_id is not None:
        row = conn.execute(text("SELECT id FROM bw_markets WHERE id = :m"), {"m": int(market_id)}).fetchone()
    elif market:
        row = conn.execute(text("""
            SELECT id FROM bw_markets WHERE LOWER(name) = LOWER(:n) OR slug = LOWER(:n)
             ORDER BY enabled DESC LIMIT 1"""), {"n": market.strip()}).fetchone()
    else:
        row = conn.execute(text("SELECT id FROM bw_markets WHERE enabled = true ORDER BY id LIMIT 1")).fetchone()
    if not row:
        raise ToolError("market not found; call list_markets for the names this site tracks")
    return int(row[0])


# ---------------------------------------------------------------------------
# Brand Watcher
# ---------------------------------------------------------------------------

async def list_brands(ctx=None) -> dict[str, Any]:
    _module_on("brand_watcher")

    def _work():
        conn = _conn()
        try:
            rows = conn.execute(text("""
                SELECT b.id, b.name, b.display_name, b.description, b.is_primary, b.enabled,
                       b.brand_keywords, b.product_keywords,
                       COALESCE((SELECT string_agg(m.name, ', ' ORDER BY m.name)
                                   FROM bw_market_brands mb JOIN bw_markets m ON m.id = mb.market_id
                                  WHERE mb.brand_id = b.id AND mb.role <> 'excluded'), '') AS markets
                  FROM bw_brands b
                 ORDER BY b.is_primary DESC, b.enabled DESC, b.display_name
            """)).mappings().all()
            return {"brands": [_plain(dict(r)) for r in rows],
                    "note": "Pass display_name as `brand` to the other brand tools. "
                            "The primary brand is the site's own; the rest are competitors."}
        finally:
            conn.close()

    return await asyncio.to_thread(_work)


async def get_brand_stats(ctx=None, brand: str | None = None, brand_id: int | None = None,
                          days_back: int = 90) -> dict[str, Any]:
    _module_on("brand_watcher")
    from app.routes.brand_watcher_routes import get_stats, get_category_distribution
    conn = _conn()
    try:
        bid, name = _brand_row(conn, brand, brand_id)
    finally:
        conn.close()
    days = max(0, min(int(days_back), 730))
    stats = await get_stats(brand_id=bid, brand_ids=None, topics=None, days_back=days, session=None)
    cats = await get_category_distribution(brand_id=bid, brand_ids=None, topics=None,
                                           days_back=days, session=None)
    return {"brand": name, "brand_id": bid, "days_back": days,
            "stats": _plain(stats), "categories": _plain(cats)}


async def get_brand_articles(ctx=None, brand: str | None = None, brand_id: int | None = None,
                             categories: str | None = None, days_back: int = 30,
                             sort_by: str = "date", page: int = 1, per_page: int = 25) -> dict[str, Any]:
    _module_on("brand_watcher")
    from app.routes.brand_watcher_routes import get_articles
    conn = _conn()
    try:
        bid, name = _brand_row(conn, brand, brand_id)
    finally:
        conn.close()
    res = await get_articles(brand_id=bid, brand_ids=None, topics=None, categories=categories,
                             days_back=max(0, min(int(days_back), 730)), sort_by=sort_by,
                             page=max(1, int(page)), per_page=max(1, min(int(per_page), 200)),
                             session=None)
    out = _plain(res)
    out["brand"] = name
    out["brand_id"] = bid
    return out


async def get_brand_perception(ctx=None, days_back: int = 90) -> dict[str, Any]:
    _module_on("brand_watcher")
    from app.routes.brand_watcher_routes import get_perception_dimensions
    res = await get_perception_dimensions(days_back=max(1, min(int(days_back), 730)), session=None)
    out = _plain(res)
    out["note"] = ("Per brand, five perception surfaces: media (news sentiment), social, community "
                   "(Reddit), employee (Glassdoor), investor. score = (positive - negative) / n x 100.")
    return out


async def get_brand_voices(ctx=None, brand: str | None = None, brand_id: int | None = None,
                           days_back: int = 90, with_digest: bool = True,
                           roles: str | None = None, posts_per_role: int = 20) -> dict[str, Any]:
    _module_on("brand_watcher")
    if os.getenv("BW_VOICES_ENABLED", "1").strip().lower() in ("0", "false", "no", "off"):
        raise ToolError("Voices is not enabled on this site")
    from app.services import audience_voices
    from app.routes.brand_watcher_routes import _voices_mention_read
    conn = _conn()
    try:
        bid, name = _brand_row(conn, brand, brand_id)
        days = max(1, min(int(days_back), 730))
        mention_read = _voices_mention_read()
        res = await asyncio.to_thread(
            audience_voices.voices, conn, brand_id=bid, display_name=name,
            days_back=days, mention_read=mention_read, min_relevance=0.4,
            per_role_limit=max(1, min(int(posts_per_role), 60)))
        wanted = [r.strip().lower() for r in (roles or "").split(",") if r.strip()] or list(res["focus"])
        if with_digest:
            res["digests"] = {}
            for role in wanted:
                if any(r["role"] == role for r in res["roles"]):
                    res["digests"][role] = await audience_voices.digest(
                        conn, brand_id=bid, display_name=name, role=role,
                        days_back=days, mention_read=mention_read)
        for r in res["roles"]:
            for p in r["posts"]:
                p["text"] = (p.get("text") or "")[:600]
        res["note"] = ("Roles come from the social evaluation of each post (patient, clinician, "
                       "customer, employee, journalist, brand ...), overridden by the author's "
                       "account profile or post history where one exists. `focus` is the pair "
                       "the Voices tab opens on. Quotes in a digest are copied from the posts.")
        return _plain(res)
    finally:
        conn.close()


async def get_brand_alerts(ctx=None, limit: int = 50, unacked_only: bool = False) -> dict[str, Any]:
    _module_on("brand_watcher")
    from app.routes.brand_watcher_routes import list_alert_events
    res = await list_alert_events(limit=max(1, min(int(limit), 200)), unacked_only=bool(unacked_only),
                                  session=None)
    return _plain(res) if isinstance(res, dict) else {"alerts": _plain(res)}


# ---------------------------------------------------------------------------
# Market Monitor
# ---------------------------------------------------------------------------

async def list_markets(ctx=None) -> dict[str, Any]:
    _module_on("market_monitor")
    from app.routes.market_monitor_routes import list_markets as _list
    res = await _list(session=None)
    return {"markets": _plain(res),
            "note": "Pass `name` as `market` (or `id` as `market_id`) to the other market tools."}


async def get_market_vendors(ctx=None, market: str | None = None, market_id: int | None = None,
                             role: str | None = None, collecting_only: bool = False) -> dict[str, Any]:
    _module_on("market_monitor")
    from app.routes.market_monitor_routes import list_vendors
    conn = _conn()
    try:
        mid = _market_id(conn, market, market_id)
    finally:
        conn.close()
    if role not in (None, "vendor", "watch", "excluded"):
        raise ToolError("role must be vendor, watch or excluded")
    res = await list_vendors(market_id=mid, role=role, collecting_only=bool(collecting_only), session=None)
    return {"market_id": mid, "vendors": _plain(res)}


async def get_market_analysis(ctx=None, market: str | None = None, market_id: int | None = None,
                              name: str | None = None, days: int | None = None) -> dict[str, Any]:
    _module_on("market_monitor")
    from app.services import market_analysis as man
    from app.routes.market_monitor_routes import _load_market
    conn = _conn()
    try:
        mid = _market_id(conn, market, market_id)
        _load_market(conn, mid)
        names = [name] if name else list(man.ANALYSES)
        bad = [n for n in names if n not in man.ANALYSES]
        if bad:
            raise ToolError(f"unknown analysis {bad[0]!r}; one of {', '.join(man.ANALYSES)}")
        out: dict[str, Any] = {"market_id": mid, "analyses": {}}
        for n in names:
            try:
                out["analyses"][n] = await asyncio.to_thread(man.run, conn, mid, n, days=days)
            except Exception as exc:  # noqa: BLE001 - one failing analysis must not blank the rest
                out["analyses"][n] = {"error": str(exc)}
        return _plain(out)
    finally:
        conn.close()


async def get_market_top_voices(ctx=None, market: str | None = None, market_id: int | None = None,
                                days: int | None = None, limit: int = 25) -> dict[str, Any]:
    _module_on("market_monitor")
    from app.routes.market_monitor_routes import market_voices
    conn = _conn()
    try:
        mid = _market_id(conn, market, market_id)
    finally:
        conn.close()
    res = await market_voices(market_id=mid, days=days, limit=max(1, min(int(limit), 200)), session=None)
    out = _plain(res)
    out["market_id"] = mid
    out["note"] = ("Accounts ranked by engagement on this market's social posts. `account.role` "
                   "is the profiled market role (vendor, vendor_staff, practitioner, "
                   "analyst_or_press ...); `audience` is which audience the account belongs to "
                   "(patient, clinician, customer ...), from the profile or from its posts.")
    return out


async def get_market_horizon(ctx=None, market: str | None = None, market_id: int | None = None) -> dict[str, Any]:
    _module_on("market_monitor")
    from app.routes.market_monitor_routes import market_horizon
    conn = _conn()
    try:
        mid = _market_id(conn, market, market_id)
    finally:
        conn.close()
    res = await market_horizon(market_id=mid, session=None)
    out = _plain(res)
    if isinstance(out, dict):
        out["market_id"] = mid
        return out
    return {"market_id": mid, "horizon": out}


async def get_market_briefings(ctx=None, market: str | None = None, market_id: int | None = None,
                               limit: int = 5) -> dict[str, Any]:
    _module_on("market_monitor")
    from app.routes.market_monitor_routes import market_briefings
    conn = _conn()
    try:
        mid = _market_id(conn, market, market_id)
    finally:
        conn.close()
    res = await market_briefings(market_id=mid, limit=max(1, min(int(limit), 120)), session=None)
    out = _plain(res)
    return out if isinstance(out, dict) else {"market_id": mid, "briefings": out}


HANDLERS = {
    "list_brands": list_brands,
    "get_brand_stats": get_brand_stats,
    "get_brand_articles": get_brand_articles,
    "get_brand_perception": get_brand_perception,
    "get_brand_voices": get_brand_voices,
    "get_brand_alerts": get_brand_alerts,
    "list_markets": list_markets,
    "get_market_vendors": get_market_vendors,
    "get_market_analysis": get_market_analysis,
    "get_market_top_voices": get_market_top_voices,
    "get_market_horizon": get_market_horizon,
    "get_market_briefings": get_market_briefings,
}
