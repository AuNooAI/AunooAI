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
import math
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


# Academic publishing platforms + journal-host domains. A brand mention on one of
# these is the publisher/citation, not third-party news coverage. Heuristic, not
# exhaustive — pair with the relevance threshold for best results.
SCHOLARLY_DOMAINS = (
    "sciencedirect.com", "link.springer.com", "springer.com", "springeropen.com",
    "onlinelibrary.wiley.com", "journals.sagepub.com", "sagepub.com",
    "tandfonline.com", "taylorfrancis.com", "plos.org", "pubs.acs.org", "acs.org",
    "mdpi.com", "academic.oup.com", "cambridge.org", "jamanetwork.com", "bmj.com",
    "thelancet.com", "cell.com", "nature.com", "frontiersin.org", "hindawi.com",
    "karger.com", "emerald.com", "ieeexplore.ieee.org", "ahajournals.org",
    "iaeme.com", "researchgate.net", "semanticscholar.org", "ssrn.com", "arxiv.org",
    "biomedcentral.com", "elifesciences.org", "pnas.org", "rsc.org", "wiley.com",
)
# Strong journal name markers (kept conservative to avoid excluding real news like
# "National Review"); require journal-ish phrasing.
SCHOLARLY_NAME_PATTERNS = (
    "proceedings", "annals of", "bulletin of", "tidende", "transactions of",
    "journal of", "review of", "acta ", "quarterly journal", "j. of",
)


def is_scholarly_source(news_source: Optional[str], url: Optional[str] = "") -> bool:
    """Heuristic: is this source an academic journal / publishing platform (i.e. the
    brand appears as publisher/citation, not as the subject of third-party news)?"""
    u = (url or "").lower()
    if any(d in u for d in SCHOLARLY_DOMAINS):
        return True
    s = (news_source or "").lower()
    if any(p in s for p in SCHOLARLY_NAME_PATTERNS):
        return True
    return False


def source_reach_weight(opoint_entities: Optional[dict]) -> float:
    """Proxy for a source's audience reach, from Opoint ``site_rank.rank_global``.

    SimilarWeb readership counts are not in the current Opoint license tier (the
    ``similarweb`` block carries only the domain), so reach is proxied by the
    publisher's global traffic rank: lower rank = more popular = higher reach.
    Returns a weight in (0, ~0.5]; ~0.49 for top-100 sites, ~0.25 at rank 10k,
    ~0.17 at rank 1M. Returns 0.0 when no rank is available.
    """
    if not isinstance(opoint_entities, dict):
        return 0.0
    sr = opoint_entities.get("site_rank") or {}
    rank = sr.get("rank_global") or sr.get("rank_country")
    try:
        rank = int(rank)
    except (TypeError, ValueError):
        return 0.0
    if rank <= 0:
        return 0.0
    return 1.0 / math.log10(rank + 10)


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
