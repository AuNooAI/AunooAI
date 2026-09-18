"""Featured items on the market front page (``market_featured``).

A hand-picked link the page promotes above the run of news: a whitepaper
we wrote, a talk, a report. Rows are added and retired with
``scripts/market_featured.py``; this module only reads them and holds the
vocabulary the renderer prints.

``placement`` says where a row goes: ``lead`` (the strip under the lead
story, every screen size), ``side`` (a card at the top of the sidebar,
desktop only) or ``both``.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from sqlalchemy import text

PLACEMENTS = ("both", "lead", "side")

#: What each kind is called on the page.
KIND_LABEL = {
    "whitepaper": "Whitepaper",
    "report": "Report",
    "talk": "Talk",
    "webinar": "Webinar",
    "article": "Article",
    "podcast": "Podcast",
}


def kind_label(kind: Optional[str]) -> str:
    return KIND_LABEL.get((kind or "").lower(), (kind or "Featured").capitalize())


def active(conn, market_id: int, *, limit: int = 3) -> List[Dict[str, Any]]:
    """The market's live featured rows, oldest ``sort_order`` first: active,
    started, and not yet ended."""
    rows = conn.execute(text("""
        SELECT id, kind, title, blurb, url, publisher, byline, vendor,
               placement, sort_order, starts_at, ends_at
          FROM market_featured
         WHERE market_id = :m AND active
           AND (starts_at IS NULL OR starts_at <= now())
           AND (ends_at IS NULL OR ends_at > now())
         ORDER BY sort_order, id
         LIMIT :n
    """), {"m": market_id, "n": limit}).mappings().all()
    return [dict(r) for r in rows]


def for_placement(rows: List[Dict[str, Any]], where: str) -> List[Dict[str, Any]]:
    """The rows that go in ``where`` (``lead`` or ``side``)."""
    return [r for r in rows if (r.get("placement") or "both") in ("both", where)]
