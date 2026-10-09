"""MCP tools for the entity layer: what the site knows about each company.

The entity layer (Entity Intelligence, ``newspec.md``) keeps, per company in
``bw_brands``: profile fields resolved from many sources with the source and
date that won (``bw_entity_canonical_fields``), dated events backed by
evidence (``bw_entity_events``), and mentions in articles and posts
(``bw_entity_mentions``). The vendor page reads the same tables through
``app/routes/market_entity_routes.py``; these tools apply the same rules:

- a field value always comes with its source and observation date;
- events marked rejected or superseded are left out, and each event carries
  how many independent sources back it;
- mentions only come from readable articles (``article_visibility``), and
  mentions nobody has evaluated are counted apart, never folded into neutral.

Nothing here starts model work, and with ``ENTITY_INTELLIGENCE_ENABLED`` off
both tools refuse, as the vendor-page routes do.
"""
from __future__ import annotations

import asyncio
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Awaitable, Callable, Optional

from sqlalchemy import text

from .errors import ToolError
from .tools import ToolSpec

_RESPONSE_BYTES = 192 * 1024
_EXCERPT_CHARS = 400
_NARRATIVE_CHARS = 6000
_EVIDENCE_PER_EVENT = 3


def _conn():
    from app.database import get_database_instance
    return get_database_instance()._temp_get_connection()


def _require_enabled() -> None:
    from app.services import entity_flags
    if not entity_flags.enabled():
        raise ToolError("entity intelligence is switched off on this site (ENTITY_INTELLIGENCE_ENABLED)")


def _plain(v: Any) -> Any:
    if isinstance(v, (datetime, date)):
        return v.isoformat()
    if isinstance(v, Decimal):
        return float(v)
    return v


def _row(r) -> dict[str, Any]:
    return {k: _plain(v) for k, v in dict(r).items()}


def _clip(s: Optional[str], n: int) -> Optional[str]:
    if s is None or len(s) <= n:
        return s
    return s[:n].rstrip() + "…"


def _markets(conn, brand_ids: list[int]) -> dict[int, list[str]]:
    if not brand_ids:
        return {}
    out: dict[int, list[str]] = {}
    for b, name in conn.execute(text("""
        SELECT mb.brand_id, m.name FROM bw_market_brands mb
          JOIN bw_markets m ON m.id = mb.market_id
         WHERE mb.brand_id = ANY(:ids) ORDER BY m.name"""), {"ids": brand_ids}).fetchall():
        out.setdefault(int(b), []).append(name)
    return out


def _list_sync(market: Optional[str], query: Optional[str], limit: int) -> dict[str, Any]:
    conn = _conn()
    try:
        where = ["(p.brand_id IS NOT NULL OR ev.n > 0 OR mn.n > 0)"]
        params: dict[str, Any] = {"lim": limit}
        if market:
            from .brand_tools import _market_id
            params["m"] = _market_id(conn, market, None)
            where.append("EXISTS (SELECT 1 FROM bw_market_brands mb WHERE mb.brand_id = b.id AND mb.market_id = :m)")
        if query:
            params["q"] = f"%{query.strip()}%"
            where.append("(b.display_name ILIKE :q OR b.name ILIKE :q)")
        rows = conn.execute(text(f"""
            SELECT b.id, b.display_name AS name, b.is_primary,
                   p.industry, p.hq_country, p.employee_count,
                   COALESCE(ev.n, 0) AS events, ev.latest AS latest_event,
                   COALESCE(mn.n, 0) AS mentions
              FROM bw_brands b
              LEFT JOIN bw_entity_profiles p ON p.brand_id = b.id
              LEFT JOIN (SELECT ee.brand_id, count(*) AS n,
                                max(COALESCE(e.occurred_at, e.first_observed_at)) AS latest
                           FROM bw_entity_event_entities ee
                           JOIN bw_entity_events e ON e.id = ee.event_id
                          WHERE e.status NOT IN ('rejected', 'superseded')
                          GROUP BY ee.brand_id) ev ON ev.brand_id = b.id
              LEFT JOIN (SELECT brand_id, count(*) AS n FROM bw_entity_mentions
                          GROUP BY brand_id) mn ON mn.brand_id = b.id
             WHERE {' AND '.join(where)}
             ORDER BY b.is_primary DESC, COALESCE(ev.n, 0) + COALESCE(mn.n, 0) DESC, b.display_name
             LIMIT :lim"""), params).mappings().all()
        entities = [_row(r) for r in rows]
        markets = _markets(conn, [e["id"] for e in entities])
        for e in entities:
            e["markets"] = markets.get(e["id"], [])
        return {
            "entities": entities,
            "note": ("Pass a name or id to get_entity for its profile, events and mentions. "
                     "events counts dated events (rejected and superseded ones left out); "
                     "mentions counts every stored mention, evaluated or not."),
        }
    finally:
        conn.close()


def _profile(conn, brand_id: int) -> dict[str, Any]:
    fields = [_row(r) for r in conn.execute(text("""
        SELECT c.field_key, c.value_text, c.value_number, c.value_date, c.unit,
               c.status, c.confidence, c.locked, c.resolved_at,
               o.source, o.observed_at, o.source_url
          FROM bw_entity_canonical_fields c
          JOIN bw_entity_observations o ON o.id = c.observation_id
         WHERE c.brand_id = :b AND c.market_id IS NULL
         ORDER BY c.field_key"""), {"b": brand_id}).mappings().all()]
    out = []
    for f in fields:
        value = f["value_number"] if f["value_number"] is not None else (f["value_date"] or f["value_text"])
        if isinstance(value, float) and value.is_integer():
            value = int(value)
        out.append({"field": f["field_key"], "value": value, "unit": f["unit"], "status": f["status"],
                    "source": f["source"], "observed_at": f["observed_at"], "source_url": f["source_url"],
                    "locked": f["locked"]})
    return {
        "fields": out,
        "conflicts": [f["field"] for f in out if f["status"] == "conflict"],
        "stale_fields": [f["field"] for f in out if f["status"] == "stale"],
        "locked_fields": [f["field"] for f in out if f["locked"]],
    }


def _events(conn, brand_id: int, days_back: int, limit: int) -> list[dict[str, Any]]:
    from app.services.article_visibility import readable_sql
    rows = conn.execute(text("""
        SELECT e.id, e.event_type, e.event_subtype, e.title, e.description,
               e.occurred_at, e.date_precision, e.corroboration, e.confidence,
               e.first_observed_at, e.why_it_matters, ee.relation,
               (SELECT count(DISTINCT independence_key) FROM bw_entity_event_evidence v
                 WHERE v.event_id = e.id AND v.relationship IN ('supports', 'originates')) AS sources
          FROM bw_entity_events e
          JOIN bw_entity_event_entities ee ON ee.event_id = e.id
         WHERE ee.brand_id = :b AND e.status NOT IN ('rejected', 'superseded')
           AND COALESCE(e.occurred_at, e.first_observed_at) >= NOW() - make_interval(days => :d)
         ORDER BY COALESCE(e.occurred_at, e.first_observed_at) DESC
         LIMIT :lim"""), {"b": brand_id, "d": days_back, "lim": limit}).mappings().all()
    events = [_row(r) for r in rows]
    if not events:
        return events
    ev = conn.execute(text(f"""
        SELECT * FROM (
            SELECT v.event_id, v.relationship, v.evidence_type, v.excerpt,
                   a.title, a.url, a.news_source, a.publication_date,
                   row_number() OVER (PARTITION BY v.event_id
                                      ORDER BY (v.relationship = 'originates') DESC, v.id) AS rn
              FROM bw_entity_event_evidence v
              LEFT JOIN articles a ON a.uri = v.article_uri
             WHERE v.event_id = ANY(:ids)
               AND (v.article_uri IS NULL OR {readable_sql('a')})
        ) x WHERE rn <= :n"""), {"ids": [e["id"] for e in events], "n": _EVIDENCE_PER_EVENT}).mappings().all()
    by_event: dict[int, list[dict[str, Any]]] = {}
    for r in ev:
        d = _row(r)
        d.pop("rn", None)
        d["excerpt"] = _clip(d.get("excerpt"), _EXCERPT_CHARS)
        by_event.setdefault(d.pop("event_id"), []).append(d)
    for e in events:
        e["description"] = _clip(e.get("description"), 800)
        e["evidence"] = by_event.get(e["id"], [])
    return events


def _mentions(conn, brand_id: int, days_back: int, limit: int) -> dict[str, Any]:
    from app.services.article_visibility import readable_sql
    summary = [_row(r) for r in conn.execute(text(f"""
        SELECT m.channel, m.platform, count(*) AS total,
               count(*) FILTER (WHERE m.status = 'pending') AS unevaluated,
               count(*) FILTER (WHERE m.sentiment ILIKE 'positive') AS positive,
               count(*) FILTER (WHERE m.sentiment ILIKE 'negative') AS negative,
               count(*) FILTER (WHERE m.stance = 'owned_claim') AS owned_claims
          FROM bw_entity_mentions m
          JOIN articles a ON a.uri = m.article_uri
         WHERE m.brand_id = :b AND m.created_at >= NOW() - make_interval(days => :d)
           AND {readable_sql('a')}
         GROUP BY 1, 2 ORDER BY 3 DESC"""), {"b": brand_id, "d": days_back}).mappings().all()]
    recent = [_row(r) for r in conn.execute(text(f"""
        SELECT m.mention_type, m.channel, m.platform, m.excerpt, m.relevance,
               m.sentiment, m.stance, m.status,
               a.title, a.url, a.news_source, a.publication_date
          FROM bw_entity_mentions m
          JOIN articles a ON a.uri = m.article_uri
         WHERE m.brand_id = :b AND m.created_at >= NOW() - make_interval(days => :d)
           AND {readable_sql('a')}
         ORDER BY a.publication_date DESC NULLS LAST, m.id DESC
         LIMIT :lim"""), {"b": brand_id, "d": days_back, "lim": limit}).mappings().all()]
    for m in recent:
        m["excerpt"] = _clip(m.get("excerpt"), _EXCERPT_CHARS)
    return {"summary": summary, "recent": recent}


def _narrative(conn, brand_id: int) -> Optional[dict[str, Any]]:
    row = conn.execute(text("""
        SELECT narrative_type, status, narrative, generated_at, date_range_start, date_range_end,
               jsonb_array_length(COALESCE(lint, '[]'::jsonb)) AS lint_problems
          FROM bw_tracker_narratives WHERE brand_id = :b
         ORDER BY (status = 'approved') DESC, generated_at DESC LIMIT 1"""), {"b": brand_id}).mappings().first()
    if not row:
        return None
    out = _row(row)
    out["narrative"] = _clip(out.get("narrative"), _NARRATIVE_CHARS)
    return out


def _get_sync(entity: Optional[str], entity_id: Optional[int], days_back: int,
              event_limit: int, mention_limit: int) -> dict[str, Any]:
    from .brand_tools import _brand_row
    conn = _conn()
    try:
        try:
            brand_id, name = _brand_row(conn, entity, entity_id)
        except ToolError:
            raise ToolError("entity not found; call list_entities for the companies this site tracks")
        out: dict[str, Any] = {
            "entity_id": brand_id, "name": name,
            "markets": _markets(conn, [brand_id]).get(brand_id, []),
            "days_back": days_back,
            "profile": _profile(conn, brand_id),
            "events": _events(conn, brand_id, days_back, event_limit),
            "mentions": _mentions(conn, brand_id, days_back, mention_limit),
            "narrative": _narrative(conn, brand_id),
        }
    finally:
        conn.close()
    out["notes"] = (
        "Profile values carry the source and date that won; status 'conflict' means sources "
        "disagree and 'stale' means the reading is old, so say so when you use one. events.sources "
        "is the number of independent sources backing an event; corroboration 'single_source' "
        "events are one outlet's claim. Mention sentiment counts leave out unevaluated mentions, "
        "which are counted apart. A narrative with status 'draft' has not been reviewed."
    )
    return out


async def list_entities(ctx=None, market: str | None = None, query: str | None = None,
                        limit: int = 50) -> dict[str, Any]:
    _require_enabled()
    return await asyncio.to_thread(_list_sync, market, query, max(1, min(int(limit or 50), 200)))


async def get_entity(ctx=None, entity: str | None = None, entity_id: int | None = None,
                     days_back: int = 180, event_limit: int = 20,
                     mention_limit: int = 10) -> dict[str, Any]:
    _require_enabled()
    if not entity and entity_id is None:
        raise ToolError("get_entity needs an entity name or entity_id; call list_entities")
    return await asyncio.to_thread(
        _get_sync, entity, entity_id, max(1, min(int(days_back or 180), 730)),
        max(0, min(int(event_limit or 0), 100)), max(0, min(int(mention_limit or 0), 50)))


SPECS: dict[str, ToolSpec] = {
    "list_entities": ToolSpec(
        name="list_entities",
        description=(
            "The companies this site holds entity data on (tracked brands and market vendors): id, "
            "name, markets, industry, HQ country, headcount, and how many dated events and "
            "mentions each has. Filter by market name or part of a company name."
        ),
        properties={
            "market": {"type": "string", "description": "Market name from list_markets. Optional."},
            "query": {"type": "string", "description": "Part of a company name. Optional."},
            "limit": {"type": "integer", "description": "Max companies (default 50, max 200).", "default": 50},
        },
        timeout=30.0,
    ),
    "get_entity": ToolSpec(
        name="get_entity",
        description=(
            "Everything the site knows about one company: profile fields (HQ, founded, headcount, "
            "funding, industry, status), each with the source and date it came from and whether "
            "sources conflict; dated events (product launches, hiring, partnerships, customer wins, "
            "funding, acquisitions) with how many independent sources back each and the evidence "
            "articles; a mention summary and the latest mentions; and the latest written narrative. "
            "Reads stored data only."
        ),
        properties={
            "entity": {"type": "string", "description": "Company name as listed by list_entities or list_brands."},
            "entity_id": {"type": "integer", "description": "Company id from list_entities, instead of a name."},
            "days_back": {"type": "integer", "description": "Window for events and mentions (default 180, max 730).", "default": 180},
            "event_limit": {"type": "integer", "description": "Max events (default 20, max 100).", "default": 20},
            "mention_limit": {"type": "integer", "description": "Max recent mentions (default 10, max 50).", "default": 10},
        },
        timeout=45.0,
        max_bytes=_RESPONSE_BYTES,
    ),
}

HANDLERS: dict[str, Callable[..., Awaitable[dict[str, Any]]]] = {
    "list_entities": list_entities,
    "get_entity": get_entity,
}
