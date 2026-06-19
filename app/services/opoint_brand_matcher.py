"""Match articles to Brand Watch brands using Opoint's resolved entities.

Opoint returns disambiguated organizations with Wikidata IDs and relevance scores
in ``articles.opoint_entities``. Matching on Wikidata IDs is far more precise than
the substring keyword matching used elsewhere — it is language-independent and free
of false positives (e.g. "Wiley" the person vs Wiley the publisher).

The brand -> Wikidata-ID mapping lives in each ``bw_brands`` row under
``config['wikidata_ids']`` so it is data-driven and editable per tenant.

The opoint_entities JSONB shape this reads:
    {"entities": {"entities": {"organization": [
        {"entity": "Wiley (publisher)", "wikidata_id": "Q1479654",
         "confidence_score": 24.1, "relevance_score": 0.64}, ...]}}, ...}
"""
import logging
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


def extract_org_entities(opoint_entities: Optional[dict]) -> List[dict]:
    """Return the list of organization entities from an article's opoint_entities,
    or [] when absent / not entity-enriched."""
    if not isinstance(opoint_entities, dict):
        return []
    inner = opoint_entities.get("entities")
    if not isinstance(inner, dict):
        return []
    ents = inner.get("entities")
    if not isinstance(ents, dict):
        return []
    orgs = ents.get("organization")
    return orgs if isinstance(orgs, list) else []


def match_brands(opoint_entities: Optional[dict],
                 brand_wikidata: Dict[str, set]) -> List[dict]:
    """Match an article's Opoint organizations against a brand -> Wikidata-IDs map.

    Args:
        opoint_entities: the article's ``opoint_entities`` JSONB value.
        brand_wikidata: ``{brand_name: {wikidata_id, ...}}``.

    Returns:
        One dict per matched brand, keeping the highest-relevance matched org:
        ``[{"brand", "relevance_score", "matched_entity", "wikidata_id"}]``.
    """
    hits: Dict[str, dict] = {}
    for org in extract_org_entities(opoint_entities):
        wid = org.get("wikidata_id")
        if not wid:
            continue
        for brand, ids in brand_wikidata.items():
            if wid in ids:
                rel = org.get("relevance_score") or 0.0
                prev = hits.get(brand)
                if prev is None or rel > prev["relevance_score"]:
                    hits[brand] = {
                        "brand": brand,
                        "relevance_score": rel,
                        "matched_entity": org.get("entity"),
                        "wikidata_id": wid,
                    }
    return list(hits.values())


def load_brand_wikidata(facade) -> Dict[str, set]:
    """Build ``{brand_name: {wikidata_id, ...}}`` from the bw_brands table.

    Reads ``config['wikidata_ids']`` per brand; brands without it are skipped.
    """
    from sqlalchemy import text
    out: Dict[str, set] = {}
    rows = facade._execute_with_rollback(
        text("SELECT name, config FROM bw_brands WHERE enabled")
    ).fetchall()
    for name, config in rows:
        ids = (config or {}).get("wikidata_ids") if isinstance(config, dict) else None
        if ids:
            out[name] = set(ids)
    return out
