"""Finding vendors the registry does not have yet.

A market registry goes stale the moment it is imported. The way new entrants
announce themselves in this category is by raising money, so funding coverage is
the discovery channel: read what the market's own collection already gathered,
pull the company being funded out of it, and check whether we know them.

Deliberately deterministic. Funding sentences are formulaic — "X raises $Y in a
Series A led by Z" — and a regex plus Opoint's resolved organizations gets the
company name without an LLM call per article. What comes out is a *candidate*,
filed as a review task with the article behind it, never a vendor added on its
own say-so.

Two things have to be filtered hard or the queue fills with noise:

- **Investors are not vendors.** Every funding story names a lead investor, and
  those names look exactly like company names.
- **Publications are not vendors.** The outlet reporting the round is an
  organization in the entity list too.
"""

import json
import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Set

from sqlalchemy import text

logger = logging.getLogger(__name__)

# An article is worth reading for a candidate only if it talks about money
# changing hands. Cheap gate before any extraction runs.
FUNDING_TRIGGER = re.compile(
    r"\b(raise[sd]?|raising|secure[sd]|land[sed]*|closes?|closed|nets?|"
    r"series\s+[a-f]\b|seed\s+(?:round|funding)|pre-seed|funding\s+round|"
    r"venture\s+round|led\s+by|oversubscribed|valuation)\b",
    re.I,
)

# "Acme raises $12M", "Acme Security secures $4.5 million".
#
# The company name keeps real capitalisation — no whole-pattern re.I, which
# would let any lowercase clause qualify as a subject. Only the verb and unit
# are case-insensitive.
_RAISE_RE = re.compile(
    r"\b([A-Z][\w&.\-]*(?:\s+[A-Z][\w&.\-]*){0,3})\s+"
    r"(?i:(?:has\s+)?(?:raise[sd]?|secure[sd]|land[sed]*|close[sd]?|net[sd]?))\s+"
    r"(?:an?\s+)?\$?\s?([\d.,]+)\s*(?i:(m|mn|million|bn|billion|k)?)\b",
)
# "$12M Series A for Acme", "$12M to Acme".
#
# The unit is case-insensitive on its own group — an uppercase "M" is the
# common form. It must NOT be a whole-pattern flag: with re.I the name group's
# [A-Z] matches lowercase too, and the pattern happily lifts a sentence
# fragment ("...to bring a faster kind of...") as a company name.
_AMOUNT_FIRST_RE = re.compile(
    r"\$\s?([\d.,]+)\s*(?i:(m|mn|million|bn|billion|k)?)[^.]{0,60}?"
    r"\b(?:for|to)\s+"
    r"([A-Z][\w&.\-]*(?:\s+[A-Z][\w&.\-]*){0,3})",
)
_ROUND_RE = re.compile(
    r"\b(pre-seed|seed|series\s+[a-f]|growth|bridge|strategic)\b", re.I)

# Investors and their kind. A funding story names one in almost every sentence,
# and the name is shaped exactly like a vendor's.
_INVESTOR_MARKERS = (
    "capital", "ventures", "venture", "partners", "equity", "fund", "funds",
    "holdings", "investment", "investments", "asset management", "advisors",
    "accelerator", "incubator", "y combinator", "andreessen", "sequoia",
    "greylock", "kleiner", "benchmark", "accel", "index", "lightspeed",
    "insight", "battery", "bessemer", "general catalyst", "khosla", "menlo",
    "redpoint", "crosslink", "team8", "cyberstarts", "glilot", "ten eleven",
    "evolution", "sorenson", "b capital", "gv", "m12", "in-q-tel",
)

# The outlet reporting the round.
_PUBLICATION_MARKERS = (
    "techcrunch", "reuters", "bloomberg", "forbes", "axios", "wired",
    "the register", "venturebeat", "sifted", "business insider", "cnbc",
    "wall street journal", "financial times", "silicon angle", "siliconangle",
    "dark reading", "the record", "cybersecurity dive", "scmagazine", "sc media",
    "help net security", "infosecurity", "the hacker news", "bleepingcomputer",
    "calcalist", "globes", "crunchbase", "pitchbook", "prnewswire",
    "businesswire", "globenewswire",
)

# Words that are never a company on their own.
_STOPWORDS = {
    "the", "a", "an", "this", "that", "it", "they", "we", "our", "its",
    "startup", "startups", "company", "companies", "firm", "vendor", "platform",
    "security", "cybersecurity", "ai", "soc", "series", "seed", "round",
    "funding", "investors", "investor", "today", "new", "israeli", "us",
    "exclusive", "report", "breaking",
}

# Words a headline puts in front of the company. "Israeli startup Radiant
# Security" is Radiant Security; carrying the descriptor into the registry
# would make the name unmatchable against every other source.
_LEADING_DESCRIPTORS = (
    "exclusive", "breaking", "report", "reports", "israeli", "american",
    "british", "french", "german", "indian", "european", "us", "uk",
    "startup", "startups", "cybersecurity", "security", "ai", "vendor",
    "company", "firm", "scaleup", "unicorn", "stealth",
)

MIN_NAME_LENGTH = 3


def _strip_descriptors(name: str) -> str:
    words = [w for w in (name or "").split() if w]
    while len(words) > 1 and words[0].lower().strip(".,") in _LEADING_DESCRIPTORS:
        words.pop(0)
    return " ".join(words)


def _looks_like_investor(name: str) -> bool:
    low = name.lower()
    return any(m in low for m in _INVESTOR_MARKERS)


def _looks_like_publication(name: str) -> bool:
    low = name.lower()
    return any(m in low for m in _PUBLICATION_MARKERS)


def _plausible_company(name: str) -> bool:
    n = (name or "").strip(" .,:;\"'")
    if len(n) < MIN_NAME_LENGTH:
        return False
    if n.lower() in _STOPWORDS:
        return False
    words = [w for w in n.split() if w]
    if not words:
        return False
    # Every word a stopword means we caught a sentence fragment, not a name.
    if all(w.lower().strip(".,") in _STOPWORDS for w in words):
        return False
    if _looks_like_investor(n) or _looks_like_publication(n):
        return False
    return True


def _normalize_amount(value: str, unit: Optional[str]) -> Optional[float]:
    """Return the amount in millions, or None when it cannot be read."""
    try:
        amount = float((value or "").replace(",", ""))
    except ValueError:
        return None
    u = (unit or "").lower()
    if u in ("bn", "billion"):
        return amount * 1000
    if u == "k":
        return amount / 1000
    return amount  # bare numbers in funding copy are millions


def extract_candidates(title: str, summary: str,
                       opoint_entities: Any = None) -> List[Dict[str, Any]]:
    """Companies a funding story appears to be about.

    Reads the headline first — funding headlines name the company being funded
    in subject position, which is exactly what the pattern below anchors on.
    Opoint's resolved organizations are added when present, but only as extra
    candidates: the entity list includes the investor and the outlet too.
    """
    blob = f"{title or ''}. {summary or ''}"
    if not FUNDING_TRIGGER.search(blob):
        return []

    round_match = _ROUND_RE.search(blob)
    round_label = round_match.group(1).title() if round_match else None

    found: Dict[str, Dict[str, Any]] = {}

    def add(name: str, amount: Optional[float], source: str) -> None:
        clean = _strip_descriptors((name or "").strip(" .,:;\"'"))
        if not _plausible_company(clean):
            return
        key = clean.lower()
        if key in found:
            if amount is not None and found[key].get("amount_musd") is None:
                found[key]["amount_musd"] = amount
            return
        found[key] = {"name": clean, "amount_musd": amount,
                      "round": round_label, "matched_by": source}

    for m in _RAISE_RE.finditer(blob):
        add(m.group(1), _normalize_amount(m.group(2), m.group(3)), "raise-pattern")
    for m in _AMOUNT_FIRST_RE.finditer(blob):
        add(m.group(3), _normalize_amount(m.group(1), m.group(2)), "amount-first")

    # Opoint organizations, when the collector supplied them.
    if opoint_entities:
        payload = opoint_entities
        if isinstance(payload, str):
            try:
                payload = json.loads(payload)
            except (ValueError, TypeError):
                payload = None
        try:
            orgs = (payload or {}).get("entities", {}).get("entities", {}).get(
                "organization", []) or []
        except AttributeError:
            orgs = []
        for org in orgs:
            if not isinstance(org, dict):
                continue
            if (org.get("relevance_score") or 0) < 0.3:
                continue
            add(org.get("entity") or "", None, "opoint")

    return list(found.values())


def _known_names(conn, market_id: int) -> Set[str]:
    """Everything the registry already answers to — names and aliases."""
    known: Set[str] = set()
    for (name,) in conn.execute(text("""
        SELECT b.display_name FROM bw_market_brands mb
        JOIN bw_brands b ON b.id = mb.brand_id
        WHERE mb.market_id = :m
    """), {"m": market_id}).fetchall():
        n = (name or "").split("(")[0].strip().lower()
        if n:
            known.add(n)
    for (value,) in conn.execute(text("""
        SELECT i.normalized_value FROM bw_vendor_identifiers i
        JOIN bw_market_brands mb ON mb.brand_id = i.brand_id
                                 AND mb.market_id = :m
        WHERE i.kind IN ('alias', 'former_name') AND i.valid_to IS NULL
    """), {"m": market_id}).fetchall():
        if value:
            known.add(value.strip().lower())
    return known


# Articles below this are in the topic by keyword accident, not by subject. A
# fibre-optics raise that mentions data centres scored 0.1 and produced a
# candidate; without a floor, every off-topic funding story in the corpus
# becomes a vendor proposal.
MIN_ALIGNMENT = 0.4


def discover_funding_candidates(conn, market_id: int, *, days: int = 14,
                                limit: int = 400,
                                min_alignment: float = MIN_ALIGNMENT,
                                dry_run: bool = False) -> Dict[str, Any]:
    """Read the market's recent funding coverage and propose new vendors.

    Files one review task per unknown company, carrying the article that named
    it. Nothing is added to the registry automatically — a funding headline is
    a lead, and a lead that turns itself into a tracked vendor is how a registry
    fills up with investors and press agencies.
    """
    topic = conn.execute(text(
        "SELECT config->'collection'->>'topic_name' FROM bw_markets WHERE id = :m"),
        {"m": market_id}).scalar()
    if not topic:
        return {"error": "This market has no collection topic yet.",
                "scanned": 0, "candidates": 0}

    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    rows = conn.execute(text("""
        SELECT uri, title, summary, publication_date, news_source, opoint_entities,
               topic_alignment_score
        FROM articles
        WHERE topic = :t AND COALESCE(publication_date, submission_date) >= :cut
          AND COALESCE(topic_alignment_score, 0) >= :floor
        ORDER BY COALESCE(publication_date, submission_date) DESC
        LIMIT :lim
    """), {"t": topic, "cut": cutoff, "lim": limit,
           "floor": min_alignment}).fetchall()

    # How much the floor is holding back, so a silent zero is legible.
    below = conn.execute(text("""
        SELECT count(*) FROM articles
        WHERE topic = :t AND COALESCE(publication_date, submission_date) >= :cut
          AND COALESCE(topic_alignment_score, 0) < :floor
    """), {"t": topic, "cut": cutoff, "floor": min_alignment}).scalar() or 0

    known = _known_names(conn, market_id)
    proposals: Dict[str, Dict[str, Any]] = {}
    scanned = 0

    for uri, title, summary, pub_date, source, entities, alignment in rows:
        scanned += 1
        for cand in extract_candidates(title or "", summary or "", entities):
            key = cand["name"].lower()
            if key in known:
                continue
            existing = proposals.get(key)
            if existing:
                existing["mentions"] += 1
                continue
            proposals[key] = {
                **cand,
                "mentions": 1,
                "article_uri": uri,
                "article_title": title,
                "news_source": source,
                "published": str(pub_date) if pub_date else None,
                "alignment": float(alignment) if alignment is not None else None,
            }

    written = 0
    if not dry_run:
        for cand in proposals.values():
            amount = cand.get("amount_musd")
            detail = ", ".join(part for part in (
                cand.get("round"),
                f"${amount}M" if amount is not None else None,
                cand.get("news_source"),
            ) if part)
            message = (
                f"{cand['name']} appears in this market's funding coverage but is "
                f"not in the registry{f' ({detail})' if detail else ''}. "
                f"Source: {cand['article_title'] or cand['article_uri']}"
            )
            conn.execute(text("""
                INSERT INTO bw_review_tasks
                    (market_id, kind, severity, field, message, source_ref)
                VALUES (:m, 'candidate_vendor', 'medium', 'registry', :msg,
                        CAST(:ref AS JSONB))
                ON CONFLICT (market_id, kind, COALESCE(brand_id, 0),
                             COALESCE(field, ''), md5(message))
                    DO UPDATE SET source_ref = EXCLUDED.source_ref,
                                  updated_at = NOW()
            """), {"m": market_id, "msg": message,
                   "ref": json.dumps(cand, default=str)})
            written += 1

    return {
        "scanned": scanned,
        "below_alignment_floor": below,
        "min_alignment": min_alignment,
        "candidates": len(proposals),
        "written": written,
        "days": days,
        "topic": topic,
        "proposals": sorted(proposals.values(),
                            key=lambda c: (-(c.get("amount_musd") or 0), c["name"])),
    }
