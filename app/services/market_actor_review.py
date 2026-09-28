"""Whether each company an item on the market page is credited to is the one
that did it.

An item is credited to a tracked vendor in two ways that can be wrong. A news
article that names the vendor is filed under it, even when the vendor is
only the platform or the partner: Synthesized's UiPath integration was listed
under UiPath, and Dear Media's podcast, hosted by a WeightWatchers employee,
under WeightWatchers. And two items that merge pool their vendors: UiPath
joined SmartBear's contract-testing launch. The first weekly sample
(27 Sep 2026) found three of its four errors of this kind.

Jev reads each source of an item and answers, for each vendor credited, whether
that company did the development or is only mentioned. The answer is stored
per article and vendor in ``bw_market_articles.review_check`` under
``actors``: ``{"<brand_id>": probability}``. The page keeps a vendor on an item
when one of its sources says so (``market_assessment._credited``); until it is
checked the item waits, like everything else the page shows.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Dict, List, Optional

from sqlalchemy import text

logger = logging.getLogger(__name__)

#: At or above this, Jev reads the company as one that did the development.
ACTOR_MIN = 0.5

_KIND_WORDS = {
    "product_launch": "a product launch", "product_expansion": "a product expansion",
    "partnership": "a partnership", "acquisition": "an acquisition",
    "funding": "a funding round", "customer": "a customer win or deployment",
    "executive_appointment": "an executive appointment", "market_exit": "a market exit",
    "market_entry": "a market entry", "research": "published research",
    "award": "an award", "contract": "a contract",
}

_QUESTION = {
    "actor": {
        "type": "noul",
        "instructions": (
            "`post` reports `development`. Is `company` one of the companies that "
            "made it happen: the one that launched, expanded, raised, acquired, "
            "was acquired, entered the partnership, hired, published or "
            "commissioned the research, survey or benchmark, or whose product "
            "the customer bought or uses? Where `post` says \"we\" or \"our\", it "
            "speaks for the account that posted it, named before the colon in "
            "its first line. A company that announces, promotes, sponsors or "
            "hosts another company's product, show or event did not do it, even "
            "on its own account (Oliver, 28 Sep 2026: WeightWatchers announcing "
            "Dear Media's podcast, hosted by a WeightWatchers executive)."),
        "criteria": {
            "true": "The post says `company` (or the account speaking as \"we\", "
                    "when that is `company`) did it: its own product, its own deal "
                    "or research, or a partnership or joint launch it is party to",
            "false": "`company` is only mentioned, or only announces, promotes, "
                     "sponsors or hosts what another company did: a platform "
                     "something integrates with, a host, an employer of someone "
                     "involved, a customer of someone else, a competitor, or not "
                     "named at all"},
    },
}


def check(source_text: str, company: str, kind: str) -> Optional[float]:
    """Jev's probability that ``company`` did the development, or None."""
    from app.services import typesafe_client
    from app.services.market_post_review import CHECK_SOURCE_CHARS

    if not typesafe_client.is_configured():
        return None
    out = typesafe_client.system_one(
        {"post": (source_text or "")[:CHECK_SOURCE_CHARS], "company": company,
         "development": _KIND_WORDS.get(kind, kind.replace("_", " "))},
        _QUESTION, use_case="services.market_actor_review:validate")
    if not out:
        return None
    return round(float(((out.get("answers") or {}).get("actor") or {}).get("noul", 0.0)), 3)


def other_names(conn, brand_ids: List[int]) -> Dict[int, List[str]]:
    """A vendor's other names: aliases, former names, its LinkedIn page and
    web domain. Louie AI posts as Graphistry, and without the name Jev said
    Louie AI had not published Graphistry's benchmark."""
    import re

    out: Dict[int, set] = {}
    for bid, kind, value in conn.execute(text("""
        SELECT brand_id, kind, coalesce(display_value, normalized_value)
          FROM bw_vendor_identifiers
         WHERE brand_id = ANY(:b) AND valid_to IS NULL
           AND kind IN ('alias', 'former_name', 'search_name', 'linkedin_company_url', 'domain')
    """), {"b": list(brand_ids)}).fetchall():
        value = value or ""
        if kind == "linkedin_company_url":
            m = re.search(r"/company/([^/?#]+)", value)
            value = m.group(1).replace("-", " ") if m else ""
        if value:
            out.setdefault(bid, set()).add(value.strip())
    return {b: sorted(v) for b, v in out.items()}


def pending(conn, market_id: int, days: int = 30) -> List[Dict[str, Any]]:
    """(article, vendor) pairs the page is waiting on."""
    from app.services import market_assessment as ma

    return ma.material_developments(conn, market_id, days).get("actors_unchecked") or []


async def review(conn, market_id: int, *, days: int = 30,
                 limit: int = 400) -> Dict[str, int]:
    """Check the credited vendors the page is waiting on, and store the answers."""
    todo = pending(conn, market_id, days)[:limit]
    stats = {"candidates": len(todo), "confirmed": 0, "rejected": 0, "unanswered": 0}
    if not todo:
        return stats
    uris = sorted({t["uri"] for t in todo})
    sources = {r["uri"]: f"{r['title'] or ''}\n\n{r['summary'] or ''}".strip()
               for r in conn.execute(text(
                   "SELECT uri, title, summary FROM articles WHERE uri = ANY(:u)"),
                   {"u": uris}).mappings()}
    from app.services.market_post_review import _CHECK_CONCURRENCY

    names = other_names(conn, sorted({t["brand_id"] for t in todo}))
    for t in todo:
        also = [n for n in names.get(t["brand_id"], []) if n.lower() != (t["vendor"] or "").lower()]
        t["company"] = f"{t['vendor']} (also publishes as: {', '.join(also)})" if also else t["vendor"]

    gate = asyncio.Semaphore(_CHECK_CONCURRENCY)

    async def one(t):
        async with gate:
            t["p"] = await asyncio.to_thread(check, sources.get(t["uri"], ""),
                                             t["company"], t["kind"])

    await asyncio.gather(*(one(t) for t in todo))
    for t in todo:
        if t.get("p") is None:
            stats["unanswered"] += 1
            continue
        stats["confirmed" if t["p"] >= ACTOR_MIN else "rejected"] += 1
        conn.execute(text("""
            UPDATE bw_market_articles
               SET review_check = jsonb_set(
                       COALESCE(review_check, '{}'::jsonb)
                       || CASE WHEN review_check ? 'actors' THEN '{}'::jsonb
                               ELSE '{"actors": {}}'::jsonb END,
                       ARRAY['actors', :b], to_jsonb(CAST(:p AS float)))
             WHERE market_id = :m AND article_uri = :u
        """), {"b": str(t["brand_id"]), "p": t["p"], "m": market_id, "u": t["uri"]})
    conn.commit()
    return stats
