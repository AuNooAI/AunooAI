"""Brand Watcher official/scholarly source collectors (per-brand opt-in).

Ports the saas.aunoo.ai official-sources design into the monolith:
  - SEC EDGAR         US company filings (financial / legal)
  - CourtListener     US court opinions / litigation
  - regulations.gov   US rulemaking / regulatory (needs REGULATIONS_GOV_API_KEY)
  - Crossref          scholarly mentions
  - OpenAlex          scholarly mentions
  - Glassdoor         employee reviews (needs OPENWEBNINJA_API_KEY;
                      openwebninja Real-Time Glassdoor Data API)

These are NOT general collectors — they are driven by the Brand Watcher monitor
loop, per-brand opt-in via ``bw_brands.config['extra_sources']`` (a list of
source keys). Per-(brand, source) ``last_polled_at`` cursors live in
``bw_brands.config['source_state']`` and gate the 24h cadence — no new table.

Records are fetched *specifically for a brand* (exact-phrase query on the
brand's primary term) and attributed directly into ``bw_article_categories``
with method 'official' and relevance 1.0 — but only after a term gate: the
brand term must appear (word-boundary) in the record's title+summary. These
APIs full-text search, so "Wiley" otherwise pulls court opinions authored by
a judge named Wiley and papers that merely cite a Wiley book; official titles
name the filer/party/work, so a real match carries the brand in the title.
Name-collision entities that legitimately carry the brand word (e.g. the
unrelated asset manager "Hotchkis & Wiley Funds") are droppable per brand via
``bw_brands.config['official_keyword_excludes']``.

Official records are stamped authoritative (factual_reporting='very high',
bias_source='official:<domain>') so authority weighting treats an SEC filing
as fact rather than an unknown 0.5 source. Landed records that match the
adverse-risk trigger gate also get a WS3 risk pass (bounded per poll).
"""

import asyncio
import json
import logging
import os
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

import httpx
from sqlalchemy import text

logger = logging.getLogger(__name__)

HTTP_TIMEOUT = 30.0
POLL_INTERVAL = timedelta(hours=24)     # min spacing per (brand, source)
INITIAL_LOOKBACK = timedelta(days=30)   # cold-start window for a newly-enabled source
MAX_RISK_LLM_CALLS_PER_POLL = 10        # bound WS3 LLM cost per poll cycle

CONTACT_EMAIL = os.getenv("OFFICIAL_SOURCES_CONTACT_EMAIL", "oliver.rochford@gmail.com")
_UA = f"Aunoo Brand Monitoring ({CONTACT_EMAIL})"

# Registry consumed by the poll loop, the status endpoint, and the UI modal.
OFFICIAL_SOURCES: Dict[str, Dict[str, Any]] = {
    "sec_edgar": {
        "label": "SEC EDGAR",
        "description": "US company filings (financial / legal)",
        "news_source": "SEC EDGAR",
        "category": "Financial Performance",
        "domain": "sec.gov",
        "requires_key": None,
    },
    "courtlistener": {
        "label": "CourtListener",
        "description": "US court opinions / litigation",
        "news_source": "CourtListener",
        "category": "Legal & Regulatory",
        "domain": "courtlistener.com",
        "requires_key": None,  # optional COURTLISTENER_API_TOKEN raises rate limit
    },
    "regulations_gov": {
        "label": "regulations.gov",
        "description": "US rulemaking / regulatory dockets",
        "news_source": "regulations.gov",
        "category": "Legal & Regulatory",
        "domain": "regulations.gov",
        "requires_key": "REGULATIONS_GOV_API_KEY",
    },
    "crossref": {
        "label": "Crossref",
        "description": "Scholarly mentions (Crossref works)",
        "news_source": "Crossref",
        "category": "Product & Innovation",
        "domain": "crossref.org",
        "requires_key": None,
    },
    "openalex": {
        "label": "OpenAlex",
        "description": "Scholarly mentions (OpenAlex works)",
        "news_source": "OpenAlex",
        "category": "Product & Innovation",
        "domain": "openalex.org",
        "requires_key": None,
    },
    "glassdoor": {
        "label": "Glassdoor",
        "description": "Employee reviews (workforce / culture signal)",
        "news_source": "Glassdoor",
        "category": "Leadership & Governance",
        "domain": "glassdoor.com",
        "requires_key": "OPENWEBNINJA_API_KEY",
        # Reviews are already company-scoped via Glassdoor company_id and
        # rarely name the employer in the review text — skip the term gate.
        "term_gate": False,
        # Anecdotal opinion, not an authoritative record — don't stamp the
        # official-source 'very high' factuality on it.
        "factuality": "mixed",
        "credibility": "medium",
    },
}


# ---------------------------------------------------------------------------
# Fetchers — each returns [{title, summary, url, author, published_at}]
# ---------------------------------------------------------------------------

def _clamp_future(pub: Optional[str]) -> Optional[str]:
    """OpenAlex carries forthcoming/placeholder dates (2049-12-31); clamp to today."""
    if not pub:
        return None
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    return today if pub[:10] > today else pub


async def _fetch_sec_edgar(term: str, since: datetime) -> List[Dict[str, Any]]:
    params = {
        "q": f'"{term}"',
        "dateRange": "custom",
        "startdt": since.strftime("%Y-%m-%d"),
        "enddt": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
    }
    headers = {"User-Agent": _UA, "Accept": "application/json"}
    async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
        resp = await client.get("https://efts.sec.gov/LATEST/search-index",
                                params=params, headers=headers)
        resp.raise_for_status()
        data = resp.json()
    out = []
    for hit in (data.get("hits", {}).get("hits", []) or []):
        src = hit.get("_source", {}) or {}
        _id = hit.get("_id") or ""
        acc, _, fname = _id.partition(":")
        ciks = src.get("ciks") or src.get("cik") or []
        cik = str(ciks[0] if isinstance(ciks, list) and ciks else "").lstrip("0")
        if cik and fname:
            url = f"https://www.sec.gov/Archives/edgar/data/{cik}/{acc.replace('-', '')}/{fname}"
        elif cik:
            url = f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK={cik}"
        else:
            continue
        form = src.get("file_type") or (src.get("forms") or [None])[0] or "Filing"
        names = src.get("display_names") or []
        filer = names[0] if names else term
        out.append({
            "title": f"{form}: {filer}",
            "summary": f"SEC {form} filing — {filer}",
            "url": url,
            "author": filer,
            "published_at": src.get("file_date"),
        })
    return out


async def _fetch_courtlistener(term: str, since: datetime) -> List[Dict[str, Any]]:
    params = {
        "q": f'"{term}"',
        "filed_after": since.strftime("%Y-%m-%d"),
        "order_by": "dateFiled desc",
        "type": "o",  # opinions
    }
    headers = {"User-Agent": _UA}
    token = os.getenv("COURTLISTENER_API_TOKEN")
    if token:
        headers["Authorization"] = f"Token {token}"
    async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
        resp = await client.get("https://www.courtlistener.com/api/rest/v4/search/",
                                params=params, headers=headers)
        resp.raise_for_status()
        data = resp.json()
    out = []
    for r in (data.get("results", []) or []):
        name = r.get("caseName") or r.get("caption")
        if not name:
            continue
        rel = r.get("absolute_url") or ""
        url = ("https://www.courtlistener.com" + rel) if rel.startswith("/") else (rel or None)
        if not url:
            continue
        court = r.get("court")
        out.append({
            "title": name,
            "summary": _strip_tags(r.get("snippet") or "") or court,
            "url": url,
            "author": court,
            "published_at": r.get("dateFiled"),
        })
    return out


async def _fetch_regulations_gov(term: str, since: datetime) -> List[Dict[str, Any]]:
    api_key = os.getenv("REGULATIONS_GOV_API_KEY")
    if not api_key:
        return []
    params = {
        "filter[searchTerm]": term,
        "filter[postedDate][ge]": since.strftime("%Y-%m-%d"),
        "page[size]": 50,
        "sort": "-postedDate",
    }
    headers = {"X-Api-Key": api_key, "User-Agent": _UA}
    async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
        resp = await client.get("https://api.regulations.gov/v4/documents",
                                params=params, headers=headers)
        resp.raise_for_status()
        data = resp.json()
    out = []
    for d in (data.get("data", []) or []):
        attrs = d.get("attributes", {}) or {}
        title = attrs.get("title")
        doc_id = d.get("id")
        if not title or not doc_id:
            continue
        doc_type = attrs.get("documentType") or "Document"
        agency = attrs.get("agencyId") or ""
        out.append({
            "title": title,
            "summary": f"{doc_type} — {agency}".strip(" —"),
            "url": f"https://www.regulations.gov/document/{doc_id}",
            "author": agency or None,
            "published_at": attrs.get("postedDate"),
        })
    return out


_JATS = re.compile(r"<[^>]+>")


def _strip_tags(s: str) -> str:
    return _JATS.sub("", s or "").strip()


def _crossref_date(published: Optional[Dict[str, Any]]) -> Optional[str]:
    parts = ((published or {}).get("date-parts") or [[]])
    dp = parts[0] if parts else []
    if not dp:
        return None
    y = dp[0]
    m = dp[1] if len(dp) > 1 else 1
    d = dp[2] if len(dp) > 2 else 1
    return f"{y:04d}-{m:02d}-{d:02d}"


async def _fetch_crossref(term: str, since: datetime) -> List[Dict[str, Any]]:
    params = {
        "query": term,
        "filter": f"from-pub-date:{since.strftime('%Y-%m-%d')}",
        "rows": 50,
        "mailto": CONTACT_EMAIL,
        "sort": "published",
        "order": "desc",
    }
    headers = {"User-Agent": f"Aunoo/1.0 (mailto:{CONTACT_EMAIL})"}
    async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
        resp = await client.get("https://api.crossref.org/works", params=params, headers=headers)
        resp.raise_for_status()
        data = resp.json()
    out = []
    for it in (data.get("message", {}).get("items", []) or []):
        titles = it.get("title") or []
        title = titles[0] if titles else None
        url = it.get("URL")
        if not title or not url:
            continue
        authors = it.get("author") or []
        author = None
        if authors:
            a0 = authors[0]
            author = " ".join(x for x in [a0.get("given"), a0.get("family")] if x) or None
        abstract = it.get("abstract")
        summary = _strip_tags(abstract) if abstract else ((it.get("container-title") or [None])[0])
        out.append({
            "title": title,
            "summary": summary,
            "url": url,
            "author": author,
            "published_at": _crossref_date(
                it.get("published") or it.get("published-online") or it.get("published-print")),
        })
    return out


def _openalex_abstract(inv: Optional[Dict[str, List[int]]]) -> Optional[str]:
    if not inv:
        return None
    positions = [(i, w) for w, idxs in inv.items() for i in idxs]
    if not positions:
        return None
    positions.sort(key=lambda p: p[0])
    return " ".join(w for _, w in positions)[:1000] or None


async def _fetch_openalex(term: str, since: datetime) -> List[Dict[str, Any]]:
    params = {
        "search": term,
        "filter": f"from_publication_date:{since.strftime('%Y-%m-%d')}",
        "per-page": 50,
        "mailto": CONTACT_EMAIL,
        "sort": "publication_date:desc",
    }
    headers = {"User-Agent": f"Aunoo/1.0 (mailto:{CONTACT_EMAIL})"}
    async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
        resp = await client.get("https://api.openalex.org/works", params=params, headers=headers)
        resp.raise_for_status()
        data = resp.json()
    out = []
    for w in (data.get("results", []) or []):
        title = w.get("title")
        url = w.get("doi") or w.get("id")
        if not title or not url:
            continue
        authorships = w.get("authorships") or []
        author = (authorships[0].get("author") or {}).get("display_name") if authorships else None
        summary = _openalex_abstract(w.get("abstract_inverted_index"))
        out.append({
            "title": title,
            "summary": summary,
            "url": url,
            "author": author,
            "published_at": w.get("publication_date"),
        })
    return out


_GLASSDOOR_API = "https://api.openwebninja.com/realtime-glassdoor-data"
# display_name -> Glassdoor company_id. Seeded from bw_brands.config
# ['glassdoor_company_id'] when set; otherwise resolved once per process
# via /company-search and cached here.
_GLASSDOOR_IDS: Dict[str, str] = {}

#: Reviews a Glassdoor company needs before name resolution will pick it on its
#: own. The noise this exists to reject sits at 0-18 reviews — florists, estate
#: agents, a satellite office, a same-named engineering firm. A brand small
#: enough to fall under this bar gets no automatic match and a log line asking
#: for config.glassdoor_company_id, rather than a confident wrong answer.
MIN_REVIEWS_FOR_AUTO_MATCH = 50


def _normalize_company_name(value: Any) -> str:
    """Company name reduced for comparison: lowercase, no punctuation, no suffix.

    'Wiley, Inc.' and 'Wiley' compare equal; 'Wiley (Australia)' does not,
    because the qualifier is what distinguishes it.
    """
    s = re.sub(r"[^\w\s]", " ", str(value or "").lower())
    s = re.sub(r"\b(inc|llc|ltd|limited|plc|corp|corporation|co|group|holdings|sons)\b", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def _shares_a_word(term_words: set, name_words: set) -> bool:
    """True when the two names have a word in common, allowing for a prefix.

    Exact word equality is too strict for the names actually in use: wbm tracks
    brand 4 as "Pearsons Education" while Glassdoor calls it "Pearson", and
    "pearson" is not "pearsons". Prefixes bridge that. The four-character floor
    keeps the rule from matching on "the" or "co".
    """
    if term_words & name_words:
        return True
    return any(
        len(t) >= 4 and len(n) >= 4 and (n.startswith(t) or t.startswith(n))
        for t in term_words for n in name_words
    )


def _name_is_compatible(term_words: set, name_words: set) -> bool:
    """False when the two names disagree about which company this is.

    Applied after ``_shares_a_word``, which only asks whether the names have a
    word in common. That is far too weak on its own: "Legion Security" shares
    "legion" with Legion Logistics, Legion Technologies and Legion Capital,
    none of them the tracked company. Observed on this market — "Daylight
    Security" resolved to Daylight Transport and then, after a re-query, to
    Daylight Donuts; "Radiant Security" to Radiant Waxing and then Radiant
    Systems. Every one of those would have put another company's employee
    rating on a vendor's page.

    Enumerating business-type words does not work, because the list is endless
    — donuts, waxing, studios, transport. The rule that does work makes no
    judgement about meaning: **every word of the shorter name must appear in
    the longer one.** A candidate is either the same name possibly extended, or
    it is a different company.

      Legion Security  vs Legion Technologies  ->  security is absent, reject
      Daylight Security vs Daylight Donuts     ->  security is absent, reject
      Pearsons Education vs Pearson            ->  pearson is present, accept
      Springer         vs Springer Nature      ->  springer is present, accept

    Prefix matching carries the same case ``_shares_a_word`` exists for, where
    the tracked name is "Pearsons" and Glassdoor's is "Pearson".
    """
    shorter, longer = ((term_words, name_words)
                       if len(term_words) <= len(name_words)
                       else (name_words, term_words))
    for word in shorter:
        if word in longer:
            continue
        if any(_prefix_match(word, other) for other in longer):
            continue
        return False
    return True


def _prefix_match(a: str, b: str) -> bool:
    """Whether two words are the same allowing a plural or short suffix.

    Four characters is the same floor ``_shares_a_word`` uses, and for the same
    reason: below it, prefixes stop being evidence.
    """
    if len(a) < 4 or len(b) < 4:
        return False
    return a.startswith(b) or b.startswith(a)


def _pick_glassdoor_company(hits: List[Dict[str, Any]], term: str) -> Optional[Dict[str, Any]]:
    """The candidate that actually IS the brand, or None.

    Glassdoor's search does not rank by relevance. For "Wiley" it returns
    "Wiley (Australia)" — 3 reviews, a different employer — ahead of the real
    "Wiley", 2435 reviews. Taking the first plausible hit therefore picks the
    wrong company roughly whenever the ordering shifts, and on 2026-08-19 it did
    on wbm: an alert told the customer their rating had fallen 3.7 → 3 and their
    business outlook 44% → 0%, when nothing had changed except which company was
    being measured.

    Name alone cannot settle it, as the live results for the tracked brands show:

      Wiley    'Wiley (Australia)' 3 reviews | 'Wiley' 2435 | 'Wiley Rein' 96
      Springer 'SPRINGER' 18 (springer.eu, an engineering firm) |
               'Springer Nature' 1729 (the publisher the customer tracks)
      Pearson  'Pearsons Estate Agents' 4 | 'Pearsons Lawyers' 2 | 'Pearson's Bakery' 3
               — the real Pearson is not in the results at all

    Matching on the name alone picks the Australian entity for Wiley and the
    engineering firm for Springer. So a candidate must first clear
    MIN_REVIEWS_FOR_AUTO_MATCH to be considered an employer worth tracking;
    among those an exact name match wins, and otherwise the most-reviewed does.
    When nothing clears the bar — Pearson — this returns None and the caller
    asks for a manual pin, which is the right answer: no Glassdoor reading beats
    a reading of somebody else's company.
    """
    term_norm = _normalize_company_name(term)
    term_words = set(term_norm.split())
    scored = []
    for h in hits:
        name = h.get("name") or h.get("company_name") or h.get("employer_name")
        cid = h.get("company_id") or h.get("id")
        if not cid or not name:
            continue
        name_norm = _normalize_company_name(name)
        if not name_norm:
            continue
        # Still require a real word in common, so a search that returns junk
        # yields nothing rather than the most-reviewed piece of junk.
        name_words = set(name_norm.split())
        if not _shares_a_word(term_words, name_words):
            continue
        # One shared word is not enough when the words that differ are what
        # distinguish the companies. "Legion Security" matched Legion Logistics
        # (taxi services, 70 reviews), "Daylight Security" matched Daylight
        # Transport (trucking), and "Radiant Security" matched Radiant Waxing —
        # each sharing its distinctive first word and differing in the one that
        # says what the company does.
        if not _name_is_compatible(term_words, name_words):
            continue
        try:
            reviews = int(h.get("review_count") or 0)
        except (TypeError, ValueError):
            reviews = 0
        if reviews < MIN_REVIEWS_FOR_AUTO_MATCH:
            continue
        scored.append((name_norm == term_norm, reviews, str(cid), h))
    if not scored:
        return None
    scored.sort(key=lambda s: (s[0], s[1]), reverse=True)
    return scored[0][3]


async def _glassdoor_company_id(client: httpx.AsyncClient, term: str,
                                headers: Dict[str, str]) -> Optional[str]:
    if term in _GLASSDOOR_IDS:
        return _GLASSDOOR_IDS[term]
    resp = await client.get(f"{_GLASSDOOR_API}/company-search",
                            params={"query": term, "limit": 5}, headers=headers)
    resp.raise_for_status()
    hits = resp.json().get("data") or []
    if isinstance(hits, dict):
        hits = hits.get("companies") or hits.get("results") or []
    best = _pick_glassdoor_company(hits, term)
    if best:
        cid = str(best.get("company_id") or best.get("id"))
        _GLASSDOOR_IDS[term] = cid
        return cid
    logger.warning(f"glassdoor: no company match for {term!r} — set "
                   f"config.glassdoor_company_id on the brand to override")
    return None


GLASSDOOR_OVERVIEW_TTL = timedelta(hours=24)
# Aggregate employer-rating fields kept from /company-overview (the rest of the
# payload — logos, job links, office lists — is display noise we don't store).
_OVERVIEW_FIELDS = [
    "company_id", "name", "rating", "review_count", "business_outlook_rating",
    "career_opportunities_rating", "ceo", "ceo_rating",
    "compensation_and_benefits_rating", "culture_and_values_rating",
    "diversity_and_inclusion_rating", "recommend_to_friend_rating",
    "senior_management_rating", "work_life_balance_rating",
    "company_size", "industry", "headquarters_location", "reviews_link",
]


async def fetch_glassdoor_overview(term: str,
                                   company_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Live aggregate employer ratings from /company-overview, or None."""
    api_key = os.getenv("OPENWEBNINJA_API_KEY")
    if not api_key:
        return None
    headers = {"x-api-key": api_key, "User-Agent": _UA}
    async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
        cid = str(company_id) if company_id else await _glassdoor_company_id(client, term, headers)
        if not cid:
            return None
        resp = await client.get(f"{_GLASSDOOR_API}/company-overview",
                                params={"company_id": cid}, headers=headers)
        resp.raise_for_status()
        data = resp.json().get("data") or {}
        if isinstance(data, list):
            data = data[0] if data else {}
        if not data:
            return None
        return {k: data.get(k) for k in _OVERVIEW_FIELDS}


def get_cached_glassdoor_overview(cfg: Dict[str, Any]) -> tuple:
    """(overview_data|None, is_fresh) from a brand's config cache."""
    entry = (cfg or {}).get("glassdoor_overview") or {}
    data = entry.get("data") or None
    fetched = entry.get("fetched_at")
    if not data or not fetched:
        return data, False
    try:
        dt = datetime.fromisoformat(fetched)
    except (ValueError, TypeError):
        return data, False
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return data, (datetime.now(timezone.utc) - dt) <= GLASSDOOR_OVERVIEW_TTL


def store_glassdoor_overview(conn, brand_id: int, data: Dict[str, Any]) -> None:
    conn.execute(text("""
        UPDATE bw_brands SET config = COALESCE(config, '{}'::jsonb)
            || jsonb_build_object('glassdoor_overview', jsonb_build_object(
                'fetched_at', CAST(:ts AS text), 'data', CAST(:d AS jsonb)))
        WHERE id = :bid
    """), {"bid": brand_id, "ts": datetime.now(timezone.utc).isoformat(),
           "d": json.dumps(data)})


def snapshot_glassdoor_overview(conn, brand_id: int, data: Dict[str, Any]) -> None:
    """Daily time-series row so rating/outlook deterioration is detectable.
    Separate transaction scope from the cache write — a missing table (pre-
    migration deploy) must not poison the overview cache commit."""
    try:
        conn.execute(text("""
            INSERT INTO bw_glassdoor_snapshots (brand_id, snapshot_date, data)
            VALUES (:bid, CURRENT_DATE, CAST(:d AS jsonb))
            ON CONFLICT (brand_id, snapshot_date) DO UPDATE SET data = EXCLUDED.data
        """), {"bid": brand_id, "d": json.dumps(data)})
        conn.commit()
    except Exception as e:
        logger.warning(f"glassdoor snapshot failed for brand {brand_id}: {e}")
        try:
            conn.rollback()
        except Exception:
            pass


async def refresh_glassdoor_overview(conn, brand_id: int, display_name: str,
                                     cfg: Dict[str, Any], force: bool = False) -> Optional[Dict[str, Any]]:
    """Cached-or-fetch employer aggregates; stores on fetch, keeps stale cache on failure."""
    cached, fresh = get_cached_glassdoor_overview(cfg)
    if fresh and not force:
        return cached
    try:
        data = await fetch_glassdoor_overview(display_name, cfg.get("glassdoor_company_id"))
    except Exception as e:
        logger.warning(f"glassdoor overview fetch failed for {display_name}: {e}")
        return cached
    if not data:
        return cached

    # Refuse a reading for a different company than the one already being
    # tracked. Name resolution only runs when no id is pinned, and it runs again
    # after every restart, so without this a lookalike can silently take over a
    # brand's rating history and the deterioration rule reads the swap as a
    # collapse. Keeping the stale cache is the safe answer: a rating that is a
    # day old beats a rating that belongs to someone else.
    pinned = str(cfg.get("glassdoor_company_id") or "").strip()
    fetched = str(data.get("company_id") or "").strip()
    if pinned and fetched and pinned != fetched:
        logger.warning(
            "glassdoor: %s resolved to company_id %s but %s is pinned — keeping the "
            "pinned company and discarding this reading", display_name, fetched, pinned)
        return cached

    store_glassdoor_overview(conn, brand_id, data)
    # Pin the company on first successful resolution. Until this existed the id
    # lived only in a per-process dict, so every restart re-ran the search and
    # could land on a different employer.
    if not pinned and fetched:
        try:
            conn.execute(text("""
                UPDATE bw_brands
                   SET config = COALESCE(config, '{}'::jsonb)
                       || jsonb_build_object('glassdoor_company_id', CAST(:cid AS text))
                 WHERE id = :bid
            """), {"bid": brand_id, "cid": fetched})
            logger.info("glassdoor: pinned %s to company_id %s", display_name, fetched)
        except Exception as e:  # noqa: BLE001 — pinning is an optimisation, not the job
            logger.warning(f"glassdoor: could not pin company_id for {display_name}: {e}")
    conn.commit()
    snapshot_glassdoor_overview(conn, brand_id, data)
    return data


async def _fetch_glassdoor(term: str, since: datetime) -> List[Dict[str, Any]]:
    api_key = os.getenv("OPENWEBNINJA_API_KEY")
    if not api_key:
        return []
    headers = {"x-api-key": api_key, "User-Agent": _UA}
    since_d = since.strftime("%Y-%m-%d")
    out: List[Dict[str, Any]] = []
    async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
        cid = await _glassdoor_company_id(client, term, headers)
        if not cid:
            return []
        for page in range(1, 4):  # up to 30 most-recent reviews per poll
            resp = await client.get(f"{_GLASSDOOR_API}/company-reviews",
                                    params={"company_id": cid, "page": page,
                                            "sort": "MOST_RECENT"},
                                    headers=headers)
            resp.raise_for_status()
            data = resp.json().get("data") or {}
            reviews = data.get("reviews") if isinstance(data, dict) else data
            if not reviews:
                break
            hit_window_edge = False
            for r in reviews:
                pub = str(r.get("review_datetime") or r.get("review_date")
                          or r.get("date") or "")[:10]
                if pub and pub < since_d:
                    hit_window_edge = True
                    break
                rating = r.get("overall_rating") or r.get("rating")
                try:
                    rating = float(rating)
                except (TypeError, ValueError):
                    rating = None
                headline = str(r.get("summary") or r.get("headline")
                               or r.get("title") or "Employee review").strip().strip('"')
                rid = r.get("review_id") or r.get("id")
                url = (r.get("review_link") or r.get("url")
                       or (f"https://www.glassdoor.com/Reviews/Employee-Review-RVW{rid}.htm" if rid else None))
                if not url:
                    continue
                parts = []
                if r.get("job_title"):
                    parts.append(f"Role: {r['job_title']}")
                if r.get("pros"):
                    parts.append(f"Pros: {r['pros']}")
                if r.get("cons"):
                    parts.append(f"Cons: {r['cons']}")
                sentiment = None
                if rating is not None:
                    sentiment = ("Positive" if rating >= 4
                                 else "Negative" if rating <= 2 else "Neutral")
                out.append({
                    "title": f"Glassdoor review{f' ({rating:.0f}/5)' if rating is not None else ''}: {headline}"[:300],
                    "summary": " | ".join(parts)[:1000] or None,
                    "url": url,
                    "author": r.get("job_title"),
                    "published_at": pub or None,
                    "sentiment": sentiment,
                })
            if hit_window_edge or len(reviews) < 10:
                break
            await asyncio.sleep(0.5)
    return out


_FETCHERS = {
    "sec_edgar": _fetch_sec_edgar,
    "courtlistener": _fetch_courtlistener,
    "regulations_gov": _fetch_regulations_gov,
    "crossref": _fetch_crossref,
    "openalex": _fetch_openalex,
    "glassdoor": _fetch_glassdoor,
}


# ---------------------------------------------------------------------------
# Poll loop internals
# ---------------------------------------------------------------------------

def _brand_terms(brand: Dict[str, Any]) -> List[str]:
    """Word-boundary matchable brand terms (for the fuzzy-source gate)."""
    terms = [brand["display_name"]]
    kw = brand.get("brand_keywords") or []
    if isinstance(kw, str):
        try:
            kw = json.loads(kw)
        except (json.JSONDecodeError, TypeError):
            kw = []
    terms.extend(k for k in kw if k and k.strip())
    return list(dict.fromkeys(t.strip() for t in terms if t.strip()))


def _term_mentioned(terms: List[str], text_l: str) -> bool:
    for t in terms:
        if re.search(r"\b" + re.escape(t.lower()) + r"\b", text_l):
            return True
    return False


def _due_since(source_state: Dict[str, Any], source: str, now: datetime,
               force: bool = False) -> Optional[datetime]:
    """The ``since`` window start for this source, or None if not due yet."""
    last = (source_state.get(source) or {}).get("last_polled_at")
    if not last:
        return now - INITIAL_LOOKBACK
    try:
        last_dt = datetime.fromisoformat(last)
    except (ValueError, TypeError):
        return now - INITIAL_LOOKBACK
    if last_dt.tzinfo is None:
        last_dt = last_dt.replace(tzinfo=timezone.utc)
    if not force and now - last_dt < POLL_INTERVAL:
        return None
    return last_dt


def _mark_polled(conn, brand_id: int, source: str, ts: datetime) -> None:
    """Merge config.source_state[source].last_polled_at without clobbering siblings."""
    conn.execute(text("""
        UPDATE bw_brands
        SET config = COALESCE(config, '{}'::jsonb)
            || jsonb_build_object(
                'source_state',
                COALESCE(config->'source_state', '{}'::jsonb)
                || jsonb_build_object(
                    CAST(:src AS text),
                    jsonb_build_object('last_polled_at', CAST(:ts AS text))
                )
            )
        WHERE id = :bid
    """), {"bid": brand_id, "src": source, "ts": ts.isoformat()})


def _land_and_attribute(conn, brand: Dict[str, Any], source_key: str,
                        rows: List[Dict[str, Any]],
                        excludes: Optional[List[str]] = None) -> List[str]:
    """Insert new articles + attribute to the brand. Returns newly-landed URIs."""
    meta = OFFICIAL_SOURCES[source_key]
    topic = f"{brand['display_name']} - Brand Watch"
    now = datetime.now(timezone.utc)
    now_iso = now.strftime("%Y-%m-%dT%H:%M:%S.%fZ")
    terms = _brand_terms(brand)
    excl = [e.lower().strip() for e in (excludes or []) if e and e.strip()]
    landed: List[str] = []
    for r in rows:
        uri = r.get("url")
        if not uri:
            continue
        text_l = f"{r.get('title') or ''} {r.get('summary') or ''}".lower()
        if meta.get("term_gate", True) and not _term_mentioned(terms, text_l):
            continue  # full-text hit that never names the brand — surname/citation noise
        if any(e in text_l for e in excl):
            continue  # known name-collision entity (config.official_keyword_excludes)
        pub = _clamp_future(r.get("published_at")) or now_iso
        inserted = conn.execute(text("""
            INSERT INTO articles (uri, title, summary, news_source,
                publication_date, submission_date, topic, category, analyzed,
                topic_alignment_score, bias, factual_reporting,
                mbfc_credibility_rating, bias_source, auto_ingested, sentiment)
            VALUES (:uri, :title, :summary, :ns, :pub, :sub, :topic, :cat, false,
                1.0, 'least biased', :fact, :cred, :bsrc, true, :sent)
            ON CONFLICT (uri) DO NOTHING
            RETURNING uri
        """), {
            "uri": uri, "title": (r.get("title") or "")[:500],
            "summary": r.get("summary"), "ns": meta["news_source"],
            "pub": pub, "sub": now_iso, "topic": topic, "cat": meta["category"],
            "fact": meta.get("factuality", "very high"),
            "cred": meta.get("credibility", "high"),
            "sent": r.get("sentiment"),
            "bsrc": f"official:{meta['domain']}",
        }).fetchone()
        if not inserted:
            continue
        conn.execute(text("""
            INSERT INTO bw_article_categories
                (article_uri, brand_id, category, classification_method,
                 confidence, relevance_score)
            VALUES (:uri, :bid, :cat, 'official', 1.0, 1.0)
            ON CONFLICT (article_uri, brand_id, category) DO NOTHING
        """), {"uri": uri, "bid": brand["id"], "cat": meta["category"]})
        landed.append(uri)
    return landed


async def _risk_pass(conn, brand: Dict[str, Any], landed_uris: List[str],
                     budget: List[int]) -> int:
    """WS3 adverse-risk pass over freshly landed official records (bounded)."""
    if not landed_uris:
        return 0
    from app.services.brand_screening import (
        RISK_TRIGGER_RE, llm_detect_risks, keyword_risk_fallback,
        store_article_risks, record_verdict)
    rows = conn.execute(text("""
        SELECT uri, title, COALESCE(summary, '') FROM articles
        WHERE uri = ANY(:uris)
    """), {"uris": landed_uris}).fetchall()
    flagged = 0
    for uri, title, summary in rows:
        if budget[0] <= 0:
            break
        blob = f"{title}. {summary}"
        if not RISK_TRIGGER_RE.search(blob):
            continue
        budget[0] -= 1
        risks = await llm_detect_risks(title or "", summary or "", brand["display_name"])
        method = "llm"
        if risks is None:
            risks = keyword_risk_fallback(blob)
            method = "keyword"
        if risks:
            store_article_risks(conn, uri, brand["id"], risks, method)
            flagged += 1
        record_verdict(conn, uri, brand["id"],
                       "risk_found" if risks else "no_risk_found", method)
    return flagged


async def poll_official_sources(db, force: bool = False,
                                only_brand_id: Optional[int] = None) -> Dict[str, Any]:
    """Poll every opted-in (brand, source) pair that is due. Safe to call often —
    the 24h cursor gate makes a no-op cycle one SELECT."""
    conn = db._temp_get_connection()
    summary: Dict[str, Any] = {"polled": 0, "new_articles": 0, "risk_flagged": 0, "errors": 0}
    risk_budget = [MAX_RISK_LLM_CALLS_PER_POLL]
    try:
        brands = conn.execute(text("""
            SELECT id, display_name, brand_keywords, COALESCE(config, '{}') AS config
            FROM bw_brands WHERE enabled = TRUE ORDER BY id
        """)).fetchall()
        now = datetime.now(timezone.utc)
        for bid, display_name, brand_keywords, config in brands:
            if only_brand_id is not None and bid != only_brand_id:
                continue
            cfg = config if isinstance(config, dict) else json.loads(config or "{}")
            enabled_sources = cfg.get("extra_sources") or []
            if not enabled_sources:
                continue
            brand = {"id": bid, "display_name": display_name,
                     "brand_keywords": brand_keywords}
            source_state = cfg.get("source_state") or {}
            for source in enabled_sources:
                fetcher = _FETCHERS.get(source)
                if fetcher is None:
                    continue
                if source == "glassdoor" and cfg.get("glassdoor_company_id"):
                    _GLASSDOOR_IDS[display_name] = str(cfg["glassdoor_company_id"])
                since = _due_since(source_state, source, now, force=force)
                if since is None:
                    continue
                try:
                    rows = await fetcher(display_name, since)
                    landed = _land_and_attribute(conn, brand, source, rows,
                                                 excludes=cfg.get("official_keyword_excludes"))
                    flagged = await _risk_pass(conn, brand, landed, risk_budget)
                    _mark_polled(conn, bid, source, now)
                    conn.commit()
                    if source == "glassdoor":
                        await refresh_glassdoor_overview(conn, bid, display_name, cfg)
                    summary["polled"] += 1
                    summary["new_articles"] += len(landed)
                    summary["risk_flagged"] += flagged
                    if landed:
                        logger.info(f"official_sources: {source} landed {len(landed)} "
                                    f"for {display_name} ({flagged} risk-flagged)")
                    await asyncio.sleep(1)  # courtesy spacing between external calls
                except Exception as e:
                    conn.rollback()
                    summary["errors"] += 1
                    logger.error(f"official_sources: brand {bid} source {source} failed: {e}")
        return summary
    finally:
        conn.close()


def official_sources_status(conn) -> List[Dict[str, Any]]:
    """Per-brand per-source status for the settings modal."""
    brands = conn.execute(text("""
        SELECT id, display_name, COALESCE(config, '{}') AS config
        FROM bw_brands WHERE enabled = TRUE ORDER BY display_name
    """)).fetchall()
    counts = {}
    for ns, bid, n in conn.execute(text("""
        SELECT a.news_source, bac.brand_id, COUNT(DISTINCT a.uri)
        FROM articles a
        JOIN bw_article_categories bac ON bac.article_uri = a.uri
        WHERE a.bias_source LIKE 'official:%'
        GROUP BY a.news_source, bac.brand_id
    """)).fetchall():
        counts[(ns, bid)] = n
    out = []
    for bid, display_name, config in brands:
        cfg = config if isinstance(config, dict) else json.loads(config or "{}")
        enabled_sources = set(cfg.get("extra_sources") or [])
        source_state = cfg.get("source_state") or {}
        sources = []
        for key, meta in OFFICIAL_SOURCES.items():
            needs_key = meta["requires_key"]
            sources.append({
                "key": key,
                "label": meta["label"],
                "description": meta["description"],
                "enabled": key in enabled_sources,
                "available": (not needs_key) or bool(os.getenv(needs_key)),
                "requires_key": needs_key,
                "last_polled_at": (source_state.get(key) or {}).get("last_polled_at"),
                "article_count": counts.get((meta["news_source"], bid), 0),
            })
        out.append({"brand_id": bid, "display_name": display_name, "sources": sources})
    return out
