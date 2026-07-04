"""Brand Watcher official/scholarly source collectors (per-brand opt-in).

Ports the saas.aunoo.ai official-sources design into the monolith:
  - SEC EDGAR         US company filings (financial / legal)
  - CourtListener     US court opinions / litigation
  - regulations.gov   US rulemaking / regulatory (needs REGULATIONS_GOV_API_KEY)
  - Crossref          scholarly mentions
  - OpenAlex          scholarly mentions

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


_FETCHERS = {
    "sec_edgar": _fetch_sec_edgar,
    "courtlistener": _fetch_courtlistener,
    "regulations_gov": _fetch_regulations_gov,
    "crossref": _fetch_crossref,
    "openalex": _fetch_openalex,
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
        if not _term_mentioned(terms, text_l):
            continue  # full-text hit that never names the brand — surname/citation noise
        if any(e in text_l for e in excl):
            continue  # known name-collision entity (config.official_keyword_excludes)
        pub = _clamp_future(r.get("published_at")) or now_iso
        inserted = conn.execute(text("""
            INSERT INTO articles (uri, title, summary, news_source,
                publication_date, submission_date, topic, category, analyzed,
                topic_alignment_score, bias, factual_reporting,
                mbfc_credibility_rating, bias_source, auto_ingested)
            VALUES (:uri, :title, :summary, :ns, :pub, :sub, :topic, :cat, false,
                1.0, 'least biased', 'very high', 'high', :bsrc, true)
            ON CONFLICT (uri) DO NOTHING
            RETURNING uri
        """), {
            "uri": uri, "title": (r.get("title") or "")[:500],
            "summary": r.get("summary"), "ns": meta["news_source"],
            "pub": pub, "sub": now_iso, "topic": topic, "cat": meta["category"],
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
    from app.routes.brand_watcher_routes import (
        _RISK_TRIGGER_RE, _llm_detect_risks, _keyword_risk_fallback,
        _store_article_risks)
    rows = conn.execute(text("""
        SELECT uri, title, COALESCE(summary, '') FROM articles
        WHERE uri = ANY(:uris)
    """), {"uris": landed_uris}).fetchall()
    flagged = 0
    for uri, title, summary in rows:
        if budget[0] <= 0:
            break
        blob = f"{title}. {summary}"
        if not _RISK_TRIGGER_RE.search(blob):
            continue
        budget[0] -= 1
        risks = await _llm_detect_risks(title or "", summary or "", brand["display_name"])
        method = "llm"
        if risks is None:
            risks = _keyword_risk_fallback(blob)
            method = "keyword"
        if risks:
            _store_article_risks(conn, uri, brand["id"], risks, method)
            flagged += 1
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
