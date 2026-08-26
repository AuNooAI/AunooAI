"""Turning provider records into rows — the half of collection that writes.

Monolith port. Shared by the market monitor loop and the Bright Data callback,
so a manual refresh and a scheduled batch land identically. Everything here is
synchronous and writes on the caller's connection; nothing commits.

The split that matters: **posts become articles, profiles become snapshots.**
A post is something the vendor published — it has a date, a URL and a body, so
it belongs in ``articles`` with every other piece of coverage, attributed
through ``bw_article_categories`` exactly as ``bw_official_sources`` does for
SEC filings. A profile is a measurement of the company. Rendering one as an
article would put a fabricated headline under a real company's name, and
nothing downstream could tell the difference afterwards.
"""

import hashlib
import json
import logging
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import text

logger = logging.getLogger(__name__)

LINKEDIN_POST_SOURCE = "linkedin_company_post"
VENDOR_WEB_SOURCE = "vendor_web"

# Bright Data pay-as-you-go: $1.50 per 1,000 records delivered, billed on
# success only, so a record returned as a provider error is not charged. This
# is the provider's published rate rather than a local preference, which is why
# it is a constant here and not an environment variable — if Bright Data
# changes the rate, this line changes with it.
PRICE_PER_1K_RECORDS_USD = 1.50

# The sources whose records come from a paid provider. Defined here because
# close_run is the one function every collector path reaches, so this is where
# a record can be priced; app.routes.market_monitor_routes imports it rather
# than keeping a second copy, so a new paid source cannot be added to one list
# and silently missed by the other.
PAID_SOURCES = frozenset({
    "linkedin_company_post", "linkedin_company_profile",
    "crunchbase_company", "linkedin_jobs",
    "pitchbook_company", "zoominfo_company", "indeed_jobs",
})

# Without an entry here a record whose text matches no category keyword is
# stored but attributed to nothing — and the Brand Watcher UI reads through
# bw_article_categories, so it would be invisible rather than uncategorised.
DEFAULT_CATEGORY: Dict[str, str] = {
    LINKEDIN_POST_SOURCE: "Product & Innovation",
    VENDOR_WEB_SOURCE: "Product & Innovation",
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def content_hash(payload: Dict[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, default=str).encode()
    ).hexdigest()


def _categorize(title: str, summary: str) -> List[str]:
    """Keyword categorisation, imported late.

    ``BW_CATEGORIES`` lives in the routes module. Importing it at module scope
    would drag the whole route tree into the monitor loop's import graph.
    """
    from app.routes.brand_watcher_routes import _categorize_article_keywords

    return _categorize_article_keywords(title or "", summary or "", {})


# ---------------------------------------------------------------------------
# Runs
# ---------------------------------------------------------------------------

def open_run(conn, *, market_id: int, source: str, provider: str,
             brand_id: Optional[int] = None, request_hash: Optional[str] = None,
             status: str = "running") -> int:
    """Record a run before the provider call, not after.

    A snapshot id that arrives with no row to attach it to is unrecoverable:
    the callback carries no session, and this row is the only thing that can
    tell it which market the records belong to.
    """
    return conn.execute(text("""
        INSERT INTO bw_collection_runs
            (market_id, brand_id, source, provider, status, request_hash)
        VALUES (:m, :b, :s, :p, :st, :rh)
        RETURNING id
    """), {"m": market_id, "b": brand_id, "s": source, "p": provider,
           "st": status, "rh": request_hash}).scalar()


def attach_job(conn, run_id: int, job_id: str) -> None:
    conn.execute(text("UPDATE bw_collection_runs SET job_id = :j WHERE id = :r"),
                 {"j": job_id, "r": run_id})


def outcome_status(received: int, stored: int, provider_errors: int = 0) -> str:
    """Map a delivered batch to a run status.

    A batch where every record is a provider error is not a success. Recording
    it as one turns source health green on a source producing nothing, which is
    exactly the signal health exists to give. Observed on the LinkedIn jobs
    dataset: 20 records received, all of them `proxy` errors, run marked
    succeeded.
    """
    if received and provider_errors >= received:
        return "failed"
    if provider_errors:
        return "partial"
    return "succeeded"


def close_run(conn, run_id: int, *, status: str, received: int = 0, new: int = 0,
              skipped: int = 0, error: Optional[str] = None,
              provider_errors: int = 0,
              cost_amount: Optional[float] = None,
              cost_currency: Optional[str] = None) -> None:
    """Close a run and price it.

    Spend is derived here rather than at the thirty-odd call sites, because
    this is the one function every collector path reaches — the same reason the
    entity hook below lives here. The price is applied from the run's own
    ``source`` inside the UPDATE, so a free internal source keeps a NULL cost
    and is distinguishable from a paid batch that happened to cost nothing.

    ``provider_errors`` is what the batch was not charged for. Bright Data
    bills on success, so a delivery of twenty records where all twenty came
    back as proxy errors costs nothing, and pricing it as twenty records would
    make the budget gate refuse work that was never paid for.

    An explicit ``cost_amount`` still wins, for the day a provider returns a
    real price with a job.
    """
    # clock_timestamp(), not NOW(): NOW() is transaction-start time, so a run
    # opened and closed inside one transaction — which is every internal
    # source — would report zero latency forever.
    conn.execute(text("""
        UPDATE bw_collection_runs
        SET status = :st, records_received = :rec, records_new = :new,
            records_skipped = :skip, error = :err,
            cost_amount = COALESCE(:cost, CASE WHEN source = ANY(:paid)
                                               THEN :billable * :unit END),
            cost_currency = COALESCE(:cur, CASE WHEN source = ANY(:paid)
                                                THEN 'USD' END),
            completed_at = clock_timestamp(),
            latency_ms = GREATEST(0, EXTRACT(EPOCH FROM
                (clock_timestamp() - started_at)) * 1000)
        WHERE id = :r
    """), {"st": status, "rec": received, "new": new, "skip": skipped,
           "err": (str(error)[:2000] if error else None), "cost": cost_amount,
           "cur": cost_currency, "r": run_id,
           "paid": list(PAID_SOURCES),
           "billable": max(0, received - max(0, provider_errors)),
           "unit": PRICE_PER_1K_RECORDS_USD / 1000.0})

    # Turn what this run collected into entity observations, links and
    # mentions. Every collector path reaches this function, so wiring it here
    # rather than at each of the twenty-seven call sites is what stops a new
    # source silently skipping the entity layer.
    #
    # It never raises and it is a no-op while ENTITY_INTELLIGENCE_ENABLED is
    # off. The provider rows are already durable above; processing them is a
    # separate concern that must not be able to fail the run that paid for
    # them.
    from app.services import entity_ingest
    entity_ingest.on_run_closed(conn, run_id, status)


def load_run(conn, run_id: int) -> Optional[Dict[str, Any]]:
    row = conn.execute(text("""
        SELECT id, market_id, brand_id, source, provider, job_id, status,
               started_at
        FROM bw_collection_runs WHERE id = :r
    """), {"r": run_id}).mappings().first()
    return dict(row) if row else None


# ---------------------------------------------------------------------------
# Snapshots
# ---------------------------------------------------------------------------

def store_snapshot(conn, *, market_id: int, brand_id: int, source: str,
                   snapshot_type: str, provider_item_id: str,
                   data: Dict[str, Any], observed_at=None, published_at=None,
                   run_id: Optional[int] = None) -> bool:
    """Insert a snapshot unless an identical one already exists.

    Identity is (source, item, content hash), so re-reading an unchanged
    profile is free and leaves no trace. A changed value produces a new row,
    and the pair is what a metric delta is computed from later.
    """
    result = conn.execute(text("""
        INSERT INTO bw_vendor_snapshots
            (market_id, brand_id, source, snapshot_type, provider_item_id,
             observed_at, published_at, data, content_hash, collection_run_id)
        VALUES (:m, :b, :src, :st, :pid, COALESCE(:obs, NOW()), :pub,
                CAST(:d AS JSONB), :h, :run)
        ON CONFLICT (source, provider_item_id, content_hash) DO NOTHING
    """), {"m": market_id, "b": brand_id, "src": source, "st": snapshot_type,
           "pid": provider_item_id, "obs": observed_at, "pub": published_at,
           "d": json.dumps(data, default=str), "h": content_hash(data),
           "run": run_id})
    return bool(result.rowcount)


# ---------------------------------------------------------------------------
# Articles
# ---------------------------------------------------------------------------

def land_article(conn, *, uri: str, title: str, summary: str, news_source: str,
                 published_at: Optional[str], topic: str,
                 category: str, bias_source: str,
                 social_meta: Optional[Dict[str, Any]] = None) -> bool:
    """Insert one article. Returns True when it was new.

    Mirrors ``bw_official_sources._land_and_attribute`` so market records look
    like every other externally-fetched record in this database. Deliberately
    *not* stamped with a credibility tier: a vendor's own post is evidence of
    what the vendor said, and stamping it authoritative would let source
    weighting treat marketing as corroboration.

    ``social_meta`` carries reach and shape for a post — likes, comments,
    shares, hashtags, post type. The provider returns all of it and we were
    dropping it on the floor, which meant we paid for the only available
    measure of whether an announcement reached anyone and then could not answer
    the question. It is updated on re-read even when the row already exists,
    because engagement is the one field on a post that genuinely changes after
    publication.
    """
    now_iso = _now_iso()
    payload = json.dumps(social_meta) if social_meta else None
    row = conn.execute(text("""
        INSERT INTO articles (uri, title, summary, news_source,
            publication_date, submission_date, topic, category, analyzed,
            topic_alignment_score, bias_source, auto_ingested, social_meta)
        VALUES (:uri, :title, :summary, :ns, :pub, :sub, :topic, :cat, false,
                1.0, :bsrc, true, CAST(:meta AS JSONB))
        ON CONFLICT (uri) DO NOTHING
        RETURNING uri
    """), {"uri": uri, "title": (title or "")[:500], "summary": summary,
           "ns": news_source, "pub": published_at or now_iso, "sub": now_iso,
           "topic": topic, "cat": category, "bsrc": bias_source,
           "meta": payload}).fetchone()
    if not row and payload:
        conn.execute(text("""
            UPDATE articles SET social_meta = CAST(:meta AS JSONB)
            WHERE uri = :uri
        """), {"uri": uri, "meta": payload})
    return bool(row)


def attribute(conn, *, brand_id: int, uri: str, title: str, summary: str,
              source: str, method: str = "market") -> int:
    """Link an article to a vendor with at least one category."""
    cats = _categorize(title, summary) or [
        DEFAULT_CATEGORY.get(source, "Media & Advertising")
    ]
    written = 0
    for cat in cats:
        conn.execute(text("""
            INSERT INTO bw_article_categories
                (article_uri, brand_id, category, classification_method,
                 confidence, relevance_score)
            VALUES (:uri, :bid, :cat, :method, 1.0, 1.0)
            ON CONFLICT (article_uri, brand_id, category) DO NOTHING
        """), {"uri": uri, "bid": brand_id, "cat": cat, "method": method})
        written += 1
    return written


# ---------------------------------------------------------------------------
# Ingest
# ---------------------------------------------------------------------------

def linkedin_url_map(conn, market_id: int) -> Tuple[Dict[str, int], Dict[int, str]]:
    """``{normalized linkedin key: brand_id}`` and ``{brand_id: display_name}``.

    Only vendors with collection switched on, so a record arriving late from a
    batch queued before an operator toggled a vendor off is discarded rather
    than charged for twice.
    """
    from app.services.brightdata_linkedin import normalize_linkedin_key

    rows = conn.execute(text("""
        SELECT i.normalized_value, i.brand_id, b.display_name
        FROM bw_vendor_identifiers i
        JOIN bw_market_brands mb ON mb.brand_id = i.brand_id
                                 AND mb.market_id = :m
        JOIN bw_brands b ON b.id = i.brand_id
        WHERE i.kind = 'linkedin_company_url' AND i.valid_to IS NULL
          AND mb.collection_enabled AND mb.role <> 'excluded'
    """), {"m": market_id}).fetchall()
    url_map: Dict[str, int] = {}
    names: Dict[int, str] = {}
    for normalized, brand_id, display_name in rows:
        key = normalize_linkedin_key(normalized)
        if key:
            url_map[key] = brand_id
        names[brand_id] = display_name
    return url_map, names


# ISO-3166 alpha-2 -> the country-name spelling already used in the registry
# import (``bw_market_brands.baseline->>'hq_country'``), so a LinkedIn-sourced
# backfill lines up with the Country filter instead of adding a second spelling
# for the same country. Covers the countries already on file for this market
# plus common vendor HQs; an unmapped code is stored as-is rather than dropped.
_LINKEDIN_COUNTRY_NAMES = {
    "US": "United States", "GB": "United Kingdom", "IL": "Israel",
    "IN": "India", "AU": "Australia", "FR": "France", "DE": "Germany",
    "ES": "Spain", "IT": "Italy", "NL": "Netherlands", "TR": "Turkey",
    "SA": "Saudi Arabia", "AE": "United Arab Emirates", "RO": "Romania",
    "BH": "Bahrain", "CA": "Canada", "SG": "Singapore",
}


def _country_name(raw: Any) -> Optional[str]:
    """One country name from LinkedIn's ``country`` field.

    The field is not always a single code. A company with offices in more than
    one country comes back comma-joined — Intezer reads ``"US,IL"`` — and
    feeding that through the name map produced the literal string ``US,IL`` in
    ``hq_country``, which matches nothing in the Vendors Country filter and is
    not the name of any country. Take the first code: where we can check it
    against the same record's ``headquarters`` field, the first code is the
    headquarters country (Intezer's reads "New York, NY", and ``US`` leads).

    A single code we have no name for is still stored as-is — "XK" in the
    filter is ugly but true and selectable, where dropping it would leave a
    blank that reads as "never collected".
    """
    if not isinstance(raw, str):
        return None
    # Some records separate with a slash rather than a comma.
    first = re.split(r"[,/]", raw)[0].strip()
    if not first:
        return None
    return _LINKEDIN_COUNTRY_NAMES.get(first.upper(), first)


def _backfill_baseline_from_profile(conn, *, market_id: int, brand_id: int,
                                    profile: Dict[str, Any]) -> None:
    """Fill in registry fields a LinkedIn profile can answer, but only the
    ones still blank.

    A vendor added through "Add vendor" gets ``baseline = {}`` — nothing ever
    filled in country, founded year or headcount for it, because those fields
    were only ever populated once, by the CSV registry import
    (``market_import.py``). The LinkedIn profile collector already fetches
    exactly this data into ``bw_vendor_snapshots`` on every run; this is what
    promotes it into the ``baseline`` fields the Vendors table and its filters
    actually read. Never overwrites a value the import (or an earlier run)
    already set — a live reading is a fallback for "we never had this",
    not a correction to a curated one.
    """
    baseline = dict(conn.execute(text("""
        SELECT baseline FROM bw_market_brands WHERE market_id = :m AND brand_id = :b
    """), {"m": market_id, "b": brand_id}).scalar() or {})
    changed = False

    country = _country_name(profile.get("country"))
    if country and not baseline.get("hq_country"):
        baseline["hq_country"] = country
        changed = True

    founded = profile.get("founded")
    if founded and not baseline.get("founded_year"):
        baseline["founded_year"] = founded
        changed = True

    employees = profile.get("employee_count")
    if employees is not None:
        metrics = dict(baseline.get("metrics") or {})
        if metrics.get("employee_count") is None:
            metrics["employee_count"] = employees
            baseline["metrics"] = metrics
            changed = True

    if changed:
        conn.execute(text("""
            UPDATE bw_market_brands SET baseline = CAST(:b AS JSONB), updated_at = NOW()
            WHERE market_id = :m AND brand_id = :bid
        """), {"b": json.dumps(baseline), "m": market_id, "bid": brand_id})


def ingest_profiles(conn, *, run: Dict[str, Any], records: List[dict],
                    url_to_brand: Dict[str, int]) -> Dict[str, int]:
    """Map Bright Data company profiles onto snapshots.

    A record whose company URL we cannot resolve is counted as unmatched rather
    than guessed at: an unresolvable profile is a broken identifier, which is a
    review task, not a measurement of some other vendor.
    """
    from app.services.brightdata_linkedin import (
        map_company_profile, normalize_linkedin_key,
    )

    stored = unchanged = unmatched = 0
    for raw in records:
        if not isinstance(raw, dict):
            continue
        mapped = map_company_profile(raw)
        key = normalize_linkedin_key(mapped.get("url"))
        brand_id = url_to_brand.get(key or "")
        if not brand_id:
            unmatched += 1
            continue
        created = store_snapshot(
            conn, market_id=run["market_id"], brand_id=brand_id,
            source="linkedin_company_profile", snapshot_type="profile",
            provider_item_id=key or str(mapped.get("company_id") or brand_id),
            data=mapped, run_id=run["id"],
        )
        if created:
            stored += 1
            _backfill_baseline_from_profile(
                conn, market_id=run["market_id"], brand_id=brand_id, profile=mapped)
        else:
            unchanged += 1
    return {"stored": stored, "unchanged": unchanged, "unmatched": unmatched}


def _post_social_meta(mapped: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Reach and shape for one post, for ``articles.social_meta``.

    Only the fields worth keeping. The mapper also returns the full post body
    and an image URL; the body is already the article summary and the image is
    of no analytic use.
    """
    engagement = mapped.get("engagement")
    engagement = engagement if isinstance(engagement, dict) else {}
    meta = {
        "platform": "linkedin",
        "author": mapped.get("author"),
        "post_type": mapped.get("post_type"),
        # Carried so the entity layer can tell the company speaking from the
        # company resharing somebody else, and from a person's post that the
        # discovery happened to return. Both were being recorded as the
        # vendor's own claim.
        "account_type": mapped.get("account_type"),
        "is_repost": mapped.get("is_repost"),
        "hashtags": (mapped.get("hashtags") or [])[:20],
        "likes": engagement.get("likes"),
        "comments": engagement.get("comments"),
        "shares": engagement.get("shares"),
        "followers": engagement.get("followers"),
    }
    # A row of nothing but nulls is worse than no row — it reads as "measured,
    # and measured zero".
    if not any(meta[k] is not None for k in
               ("likes", "comments", "shares", "followers")) \
            and not meta["hashtags"] and not meta["post_type"]:
        return None
    return {k: v for k, v in meta.items() if v is not None and v != []}


def ingest_posts(conn, *, run: Dict[str, Any], records: List[dict],
                 url_to_brand: Dict[str, int],
                 brand_names: Dict[int, str]) -> Dict[str, int]:
    """Map company posts onto articles and attribute them.

    Attribution is direct: we asked for this company's page, so a post from it
    is that company's. No term gate — unlike a full-text search against SEC or
    Crossref, a vendor's own post routinely never names the vendor.
    """
    from app.services.brightdata_linkedin import (
        map_company_post, normalize_linkedin_key,
    )

    stored = attributed = dropped = unmatched = 0
    for raw in records:
        if not isinstance(raw, dict):
            continue
        mapped = map_company_post(raw)
        if not mapped:
            # No stable id or no text: an item we cannot dedup would re-land on
            # every single run.
            dropped += 1
            continue
        key = normalize_linkedin_key(mapped.get("company_url"))
        brand_id = url_to_brand.get(key or "")
        uri = mapped.get("url")
        if not brand_id or not uri:
            unmatched += 1
            continue
        display_name = brand_names.get(brand_id, "")
        published = mapped.get("published_at")
        is_new = land_article(
            conn, uri=uri, title=mapped["title"], summary=mapped.get("summary"),
            news_source="linkedin", topic=f"{display_name} - Brand Watch",
            published_at=(published.strftime("%Y-%m-%dT%H:%M:%S.%fZ")
                          if isinstance(published, datetime) else None),
            category="Product & Innovation", bias_source="vendor:linkedin",
            social_meta=_post_social_meta(mapped),
        )
        if is_new:
            stored += 1
        # Attribute on every pass, not just the first: an article that landed
        # before this vendor joined the market still needs the link.
        attributed += 1 if attribute(
            conn, brand_id=brand_id, uri=uri, title=mapped["title"],
            summary=mapped.get("summary") or "", source=LINKEDIN_POST_SOURCE,
        ) else 0
    return {"stored": stored, "attributed": attributed,
            "dropped": dropped, "unmatched": unmatched}


# ---------------------------------------------------------------------------
# Collection setup — market terms, not 82 vendor names
# ---------------------------------------------------------------------------
#
# The point of a market is to report on the market. What gets collected is
# therefore the market's own language — "SOC automation", "autonomous SOC",
# "alert triage AI" — and the vendor registry is what we measure that coverage
# against, not 82 separate things to monitor.
#
# Searching all 82 names instead would be worse on every axis. A third of this
# registry is single-word and several are ordinary words (Nua, Joon, Mave,
# Cantina), so it pulls a media company, a first name and a restaurant. It
# spends provider quota proportional to registry size. And it answers the wrong
# question: a market brief is about where the category is moving, not about who
# was mentioned most often.
#
# Vendor names stay available as an opt-in second set for the cases where a
# specific company's coverage matters — but they are off by default.

# Sensible starting terms when a market has none configured. Editable per
# market through ``bw_markets.config['collection_terms']``.
DEFAULT_MARKET_TERMS: List[str] = []

# Ordinary words that happen to be vendor names. Bare, each one is a noise
# generator; the length check below also catches anything short.
_AMBIGUOUS_NAMES = {
    "nua", "joon", "mave", "zaun", "cantina", "mate", "beacon", "sevii",
    "crogl", "prophet", "radiant", "method", "variance", "intrinsic",
    "andesite", "almanax", "opnova", "cotool", "elezar",
}

# Appended to an ambiguous name so the collector requires both words.
DEFAULT_QUALIFIER = "security"

# Below this, a single-word name is too short to stand alone whatever it says.
MIN_STANDALONE_LENGTH = 6


# Vendor names that are also ordinary English words. Deliberately narrower
# than ``_AMBIGUOUS_NAMES`` above, which is a *collection search* list: a
# search provider returns junk for a short query whatever the word is, so that
# list includes distinctive-but-short names like "crogl" and "opnova".
#
# Classification is a different problem. It matches against an article already
# in hand, with word boundaries, so a short distinctive name is safe — measured
# against 48,012 analysed articles, "Crogl" matched none and "7ai" matched one.
# Only real words still over-match: "Intrinsic" 15 and "Variance" 13, none of
# them about either company. Qualifying the distinctive names as well would
# make the classifier miss the mentions it exists to find.
_WORD_NAMES = {
    "variance", "intrinsic", "prophet", "beacon", "method", "radiant",
    "cantina", "mate", "sage", "spark", "summit", "vertex", "apex",
}


def brand_keywords_for_vendor(display_name: str, aliases=(),
                              qualifier: str = DEFAULT_QUALIFIER) -> List[str]:
    """Keywords safe to hand Brand Watcher's classifier for one vendor.

    Different job from ``keyword_for_vendor``, which builds a *search* term for
    a collection provider. This builds the list the classifier matches against
    an article it already has, and the failure mode is the same one in reverse:
    an ordinary word used as a company name attributes unrelated articles to
    that company.

    A multi-word name is specific enough on its own. A single word gets the
    qualifier only when it is a word in its own right.
    """
    names = [n for n in ([display_name] + list(aliases)) if n and n.strip()]
    out: List[str] = []
    for raw in names:
        name = raw.split("(")[0].strip() if "(" in raw else raw.strip()
        if not name:
            continue
        needs_qualifier = " " not in name and name.lower() in _WORD_NAMES
        term = f"{name} {qualifier}" if needs_qualifier else name
        if term not in out:
            out.append(term)
    return out


def keyword_for_vendor(display_name: str, qualifier: str = DEFAULT_QUALIFIER) -> tuple:
    """Return ``(keyword, qualified)`` for one vendor name.

    A multi-word name is already specific enough to stand alone. A single word
    is only safe when it is long and not an ordinary word; otherwise it gets a
    qualifier so the collector demands both terms.
    """
    name = (display_name or "").strip()
    # Drop a parenthetical: "Variance (was Intrinsic)" searches as "Variance".
    if "(" in name:
        name = name.split("(")[0].strip()
    if not name:
        return "", False
    if " " in name:
        return name, False
    if len(name) >= MIN_STANDALONE_LENGTH and name.lower() not in _AMBIGUOUS_NAMES:
        return name, False
    return f"{name} {qualifier}", True


# The keyword normalizer truncates anything longer at the last word boundary,
# so a term written past this length silently becomes a shorter, broader one —
# "threat detection startup Series A" collects as "threat detection startup".
MAX_KEYWORD_CHARS = 30


def check_term(term: str) -> Optional[str]:
    """Return what a term will actually be searched as, if it differs."""
    t = (term or "").strip()
    if len(t) <= MAX_KEYWORD_CHARS:
        return None
    cut = t[:MAX_KEYWORD_CHARS]
    space = cut.rfind(" ")
    return (cut[:space] if space > MAX_KEYWORD_CHARS // 2 else cut).strip()


def market_terms(conn, market_id: int) -> List[str]:
    """The market's own search language, from its config."""
    cfg = conn.execute(text(
        "SELECT config FROM bw_markets WHERE id = :m"), {"m": market_id}).scalar()
    cfg = cfg if isinstance(cfg, dict) else {}
    terms = cfg.get("collection_terms")
    if isinstance(terms, list):
        return [str(t).strip() for t in terms if str(t).strip()]
    return list(DEFAULT_MARKET_TERMS)


# Which vendors get searched by name alongside the market's own terms.
#   none   — market language only
#   funded — vendors with a disclosed raise. The ones with money are the ones
#            shipping, hiring and being written about, so this is the set worth
#            paying to follow by name.
#   all    — every active vendor, including the ones nobody covers
VENDOR_NAME_MODES = ("none", "funded", "all")
DEFAULT_VENDOR_NAME_MODE = "funded"


def plan_market_keywords(conn, market_id: int,
                         qualifier: str = DEFAULT_QUALIFIER,
                         vendor_names: str = DEFAULT_VENDOR_NAME_MODE
                         ) -> Dict[str, Any]:
    """What a market's collection group would search for. Reads only.

    The market's own language always. Vendor names by mode — funded by default,
    because a raise is the best available proxy for a vendor being active
    enough to generate coverage, and searching all 82 spends quota on companies
    nobody writes about.
    """
    if vendor_names not in VENDOR_NAME_MODES:
        vendor_names = DEFAULT_VENDOR_NAME_MODE

    terms = market_terms(conn, market_id)
    keywords: List[str] = list(dict.fromkeys(terms))
    qualified: List[str] = []
    vendor_keywords: List[str] = []

    rows = conn.execute(text("""
        SELECT b.display_name,
               mb.baseline->'funding_baseline'->>'status' AS funding_status,
               (mb.baseline->'funding_baseline'->>'total_musd')::numeric AS raised
        FROM bw_market_brands mb
        JOIN bw_brands b ON b.id = mb.brand_id
        WHERE mb.market_id = :m AND mb.collection_enabled
          AND mb.role <> 'excluded'
        ORDER BY mb.sort_order
    """), {"m": market_id}).fetchall()

    if vendor_names != "none":
        for display_name, funding_status, raised in rows:
            if vendor_names == "funded" and (funding_status or "") != "Disclosed":
                continue
            kw, was_qualified = keyword_for_vendor(display_name, qualifier)
            if not kw or kw in keywords:
                continue
            keywords.append(kw)
            vendor_keywords.append(kw)
            if was_qualified:
                qualified.append(kw)

    # Surface truncation rather than letting a term quietly broaden.
    truncated = [
        {"term": term, "searched_as": shortened}
        for term in keywords
        for shortened in [check_term(term)] if shortened
    ]

    return {
        "market_terms": terms,
        "truncated": truncated,
        "vendor_keywords": vendor_keywords,
        "keywords": keywords,
        "qualified": qualified,
        "vendors": len(rows),
        "funded_vendors": sum(1 for _, s, _r in rows if (s or "") == "Disclosed"),
        "qualifier": qualifier,
        "vendor_names": vendor_names,
    }


def setup_market_collection(conn, db, market_id: int, market_name: str, *,
                            qualifier: str = DEFAULT_QUALIFIER,
                            vendor_names: str = DEFAULT_VENDOR_NAME_MODE,
                            dry_run: bool = True) -> Dict[str, Any]:
    """Create (idempotently) the market's collection topic and keyword group.

    Two things have to exist together. The keyword group is what collects; the
    config.json topic is what lets the analysis step enrich what was collected.
    A group with no matching topic collects forever and enriches nothing, and
    does it silently.
    """
    plan = plan_market_keywords(conn, market_id, qualifier, vendor_names)
    group_name = f"{market_name} - Market Watch"
    topic_name = f"Market Monitoring {market_name}"
    plan.update({"group_name": group_name, "topic_name": topic_name,
                 "dry_run": dry_run})
    if not plan["keywords"]:
        # No terms means no collection. Creating an empty group would leave a
        # market that looks configured and gathers nothing.
        plan["error"] = (
            "This market has no collection terms. Add them under "
            "config.collection_terms before setting collection up."
        )
        return plan
    if dry_run:
        return plan

    import json as _json
    import os

    from app.database_query_facade import DatabaseQueryFacade
    from app.routes.brand_watcher_routes import BW_CATEGORIES, normalize_keyword_list

    # 1. Topic in config.json. This file is live, UI-edited state, so it is
    #    written atomically and only ever appended to.
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    config_path = os.path.join(base_dir, "config", "config.json")
    with open(config_path) as f:
        config = _json.load(f)
    existing = [t["name"] for t in config.get("topics", [])]
    topic_created = False
    if topic_name not in existing:
        standard = config["topics"][0] if config.get("topics") else {}
        config["topics"].append({
            "name": topic_name,
            "description": (
                f"Market monitoring topic for {market_name}. Tracks vendor "
                "coverage, positioning and material change across the market's "
                "registry."
            ),
            "categories": list(BW_CATEGORIES.keys()),
            "future_signals": [
                "Vendor gaining momentum", "Vendor losing momentum",
                "New entrant", "Consolidation underway",
                "Category boundary shifting", "Funding cycle turning",
                "Customer adoption accelerating", "Competitive threat detected",
            ],
            "sentiment": standard.get("sentiment", [
                "Optimistic", "Cautious", "Neutral", "Concerned", "Pessimistic"]),
            "time_to_impact": standard.get("time_to_impact", [
                "Immediate", "Short-term", "Mid-term", "Long-term"]),
            "driver_types": standard.get("driver_types", [
                "Catalyst", "Accelerator", "Delayer", "Blocker", "Initiator",
                "Terminator", "Unknown"]),
        })
        temp_path = f"{config_path}.temp"
        with open(temp_path, "w") as f:
            _json.dump(config, f, indent=2)
        os.replace(temp_path, config_path)
        topic_created = True
        logger.info("market %s: created config topic '%s'", market_id, topic_name)

    # 2. Keyword group, replacing its keywords on a re-run so a vendor toggled
    #    off stops being searched for.
    facade = DatabaseQueryFacade(db, logger)
    group = facade.get_keyword_group_id_by_name_and_topic(group_name, topic_name)
    group_created = False
    if group:
        group_id = group[0]
        facade.delete_group_keywords(group_id)
    else:
        group_id = facade.create_group(group_name, topic_name)
        group_created = True

    normalized = normalize_keyword_list(plan["keywords"])
    for kw in normalized:
        facade.add_keywords_to_group(group_id, kw)

    conn.execute(text("""
        UPDATE bw_markets
        SET config = COALESCE(config, '{}'::jsonb) || CAST(:p AS JSONB),
            updated_at = NOW()
        WHERE id = :m
    """), {"m": market_id, "p": _json.dumps({
        "collection": {"group_id": group_id, "group_name": group_name,
                       "topic_name": topic_name, "keywords": len(normalized),
                       "qualifier": qualifier,
                       "vendor_names": vendor_names},
    })})

    plan.update({"group_id": group_id, "group_created": group_created,
                 "topic_created": topic_created,
                 "keywords_written": len(normalized)})
    return plan


# ---------------------------------------------------------------------------
# Crunchbase and job listings
# ---------------------------------------------------------------------------

CRUNCHBASE_SOURCE = "crunchbase_company"
JOBS_SOURCE = "linkedin_jobs"
PITCHBOOK_SOURCE = "pitchbook_company"
ZOOMINFO_SOURCE = "zoominfo_company"
INDEED_SOURCE = "indeed_jobs"


def crunchbase_url_map(conn, market_id: int) -> Dict[str, int]:
    """``{canonical crunchbase url: brand_id}`` for collecting vendors."""
    from app.services.brightdata_linkedin import normalize_crunchbase_key

    rows = conn.execute(text("""
        SELECT i.normalized_value, i.brand_id
        FROM bw_vendor_identifiers i
        JOIN bw_market_brands mb ON mb.brand_id = i.brand_id AND mb.market_id = :m
        WHERE i.kind = 'crunchbase_url' AND i.valid_to IS NULL
          AND mb.collection_enabled AND mb.role <> 'excluded'
    """), {"m": market_id}).fetchall()
    out: Dict[str, int] = {}
    for value, brand_id in rows:
        key = normalize_crunchbase_key(value)
        if key:
            out[key] = brand_id
    return out


def identifier_url_map(conn, market_id: int, kind: str) -> Dict[str, int]:
    """``{url: brand_id}`` for vendors with a manually-recorded identifier of
    this kind.

    Unlike ``crunchbase_url_map``, there is no guess here and no
    normalisation — PitchBook and ZoomInfo profile URLs end in an opaque
    numeric id that cannot be derived from a company name, so a vendor has
    one only if an operator entered it. Whatever they typed is what gets
    collected.
    """
    rows = conn.execute(text("""
        SELECT i.normalized_value, i.brand_id
        FROM bw_vendor_identifiers i
        JOIN bw_market_brands mb ON mb.brand_id = i.brand_id AND mb.market_id = :m
        WHERE i.kind = :k AND i.valid_to IS NULL
          AND mb.collection_enabled AND mb.role <> 'excluded'
    """), {"m": market_id, "k": kind}).fetchall()
    return {value: brand_id for value, brand_id in rows if value}


def ingest_crunchbase(conn, *, run: Dict[str, Any], records: List[dict],
                      url_to_brand: Dict[str, int]) -> Dict[str, int]:
    """Store funding records, and fold the durable facts into the registry.

    The snapshot is the dated observation. The baseline gets the handful of
    fields a vendor table and a filter actually read — round count, last round
    type, investors, and Crunchbase's momentum scores. Dollar amounts are not
    among them because this dataset does not carry any.
    """
    from app.services.brightdata_linkedin import (
        map_crunchbase_company, normalize_crunchbase_key,
    )

    stored = unchanged = unmatched = 0
    for raw in records:
        if not isinstance(raw, dict):
            continue
        key = normalize_crunchbase_key(
            (raw.get("input") or {}).get("url") if isinstance(raw.get("input"), dict)
            else None) or normalize_crunchbase_key(raw.get("url"))
        brand_id = url_to_brand.get(key or "")
        mapped = map_crunchbase_company(raw)
        if not brand_id or not mapped:
            unmatched += 1
            continue

        if store_snapshot(
            conn, market_id=run["market_id"], brand_id=brand_id,
            source=CRUNCHBASE_SOURCE, snapshot_type="funding",
            provider_item_id=key or mapped["crunchbase_id"] or str(brand_id),
            data=mapped, run_id=run["id"],
        ):
            stored += 1
        else:
            unchanged += 1

        conn.execute(text("""
            UPDATE bw_market_brands
            SET baseline = baseline || jsonb_build_object('funding_crunchbase',
                                                          CAST(:p AS JSONB)),
                updated_at = NOW()
            WHERE market_id = :m AND brand_id = :b
        """), {"m": run["market_id"], "b": brand_id, "p": json.dumps({
            "rounds": mapped["num_funding_rounds"],
            "last_round": mapped["last_funding_type"],
            "investors": mapped["num_investors"],
            "lead_investors": mapped["lead_investors"],
            "ipo_status": mapped["ipo_status"],
            "operating_status": mapped["operating_status"],
            "growth_score": mapped["growth_score"],
            "heat_score": mapped["heat_score"],
            "cb_rank": mapped["cb_rank"],
            "observed_at": datetime.now(timezone.utc).isoformat(),
        }, default=str)})
    return {"stored": stored, "unchanged": unchanged, "unmatched": unmatched}


def ingest_jobs(conn, *, run: Dict[str, Any], records: List[dict],
                url_to_brand: Dict[str, int]) -> Dict[str, int]:
    """Store job listings as hiring observations, one per posting."""
    from app.services.brightdata_linkedin import (
        map_job_listing, normalize_linkedin_key,
    )

    stored = unchanged = unmatched = 0
    provider_errors = sum(
        1 for r in records
        if isinstance(r, dict) and (r.get("error") or r.get("error_code")))
    for raw in records:
        if not isinstance(raw, dict):
            continue
        mapped = map_job_listing(raw)
        if not mapped:
            unmatched += 1
            continue
        key = normalize_linkedin_key(mapped.get("company_url"))
        brand_id = url_to_brand.get(key or "")
        if not brand_id:
            unmatched += 1
            continue
        if store_snapshot(
            conn, market_id=run["market_id"], brand_id=brand_id,
            source=JOBS_SOURCE, snapshot_type="job_posting",
            provider_item_id=mapped["posting_id"], data=mapped, run_id=run["id"],
        ):
            stored += 1
        else:
            unchanged += 1
    return {"stored": stored, "unchanged": unchanged, "unmatched": unmatched,
            "provider_errors": provider_errors}


def ingest_pitchbook(conn, *, run: Dict[str, Any], records: List[dict],
                     url_to_brand: Dict[str, int]) -> Dict[str, int]:
    """Store PitchBook records as firmographic snapshots.

    Same attribution shape as ``ingest_crunchbase`` — a straight collect by
    URL, matched back to a vendor via the URL Bright Data echoes in
    ``input``/``discovery_input``, not by name.
    """
    from app.services.brightdata_linkedin import map_pitchbook_company

    stored = unchanged = unmatched = 0
    for raw in records:
        if not isinstance(raw, dict):
            continue
        inp = raw.get("input") or raw.get("discovery_input")
        url = (inp or {}).get("url") if isinstance(inp, dict) else raw.get("url")
        brand_id = url_to_brand.get(url or "")
        mapped = map_pitchbook_company(raw)
        if not brand_id or not mapped:
            unmatched += 1
            continue
        if store_snapshot(
            conn, market_id=run["market_id"], brand_id=brand_id,
            source=PITCHBOOK_SOURCE, snapshot_type="firmographic",
            provider_item_id=url or str(brand_id), data=mapped, run_id=run["id"],
        ):
            stored += 1
        else:
            unchanged += 1
    return {"stored": stored, "unchanged": unchanged, "unmatched": unmatched}


def ingest_zoominfo(conn, *, run: Dict[str, Any], records: List[dict],
                    url_to_brand: Dict[str, int]) -> Dict[str, int]:
    """Store ZoomInfo records as firmographic snapshots. Same shape as
    ``ingest_pitchbook``."""
    from app.services.brightdata_linkedin import map_zoominfo_company

    stored = unchanged = unmatched = 0
    for raw in records:
        if not isinstance(raw, dict):
            continue
        inp = raw.get("input") or raw.get("discovery_input")
        url = (inp or {}).get("url") if isinstance(inp, dict) else raw.get("url")
        brand_id = url_to_brand.get(url or "")
        mapped = map_zoominfo_company(raw)
        if not brand_id or not mapped:
            unmatched += 1
            continue
        if store_snapshot(
            conn, market_id=run["market_id"], brand_id=brand_id,
            source=ZOOMINFO_SOURCE, snapshot_type="firmographic",
            provider_item_id=url or str(brand_id), data=mapped, run_id=run["id"],
        ):
            stored += 1
        else:
            unchanged += 1
    return {"stored": stored, "unchanged": unchanged, "unmatched": unmatched}


def ingest_indeed_jobs(conn, *, run: Dict[str, Any],
                       records: List[dict]) -> Dict[str, int]:
    """Store Indeed listings as hiring observations, pooled with LinkedIn's
    under the same ``job_posting`` snapshot type — two views of the same
    signal, kept apart only by ``source`` and ``provider_item_id``'s separate
    id namespace, so neither can collide with or double the other.

    Attribution is the ``company_name`` Indeed reports, checked against the
    vendor with ``employer_matches``. The previous plan read
    ``discovery_input.posted_by``; the dataset sample shows ``discovery_input``
    arriving as ``null``, so every record would have gone unmatched — the safe
    failure that was documented, and still a collector returning nothing.

    The check matters because ``keyword_search`` matches job titles as well as
    company names, so a search for one vendor legitimately returns other
    employers' listings. Anything whose reported employer does not contain every
    identifying word of the vendor's name is dropped, and the count is logged
    rather than left to look like an empty market.
    """
    from app.services.brightdata_linkedin import (employer_matches,
                                                  map_indeed_job)

    name_to_brand = {
        name.split("(")[0].strip().lower(): brand_id
        for name, brand_id in conn.execute(text("""
            SELECT b.display_name, b.id FROM bw_brands b
            JOIN bw_market_brands mb ON mb.brand_id = b.id
                                     AND mb.market_id = :m
        """), {"m": run["market_id"]}).fetchall()
    }

    stored = unchanged = unmatched = expired = 0
    # A record the provider could not fetch is not a listing we looked for and
    # did not find. Without this the run closes as `succeeded` with nothing
    # stored, which reads as "Indeed ran and this market has no jobs" — the
    # measured-zero claim the whole metric contract exists to prevent.
    #
    # Not hypothetical: the first live control returned five records for
    # Louisiana-Pacific and every one was `{"error": "Crawler error: ...too
    # many requests", "error_code": "rate_limit"}`. ``ingest_jobs`` has counted
    # these since the LinkedIn dataset did the same thing with `proxy` errors;
    # this ingest was written without it.
    provider_errors = sum(
        1 for r in records
        if isinstance(r, dict) and (r.get("error") or r.get("error_code")))
    for raw in records:
        if not isinstance(raw, dict):
            continue
        mapped = map_indeed_job(raw)
        if not mapped:
            unmatched += 1
            continue
        # An expired listing is not an open role. Kept out rather than stored
        # and filtered later, because the hiring counts read every stored
        # job_posting row and would include it.
        if mapped.get("is_expired"):
            expired += 1
            continue

        # Attribution is the employer Indeed reports, checked against the
        # vendor we searched for. `discovery_input` was the previous plan and
        # the dataset sample shows it arriving as null, so nothing would have
        # matched. `company_name` is the field that is populated.
        #
        # The check is not a formality: `keyword_search` matches job titles as
        # well as companies, so a search for one vendor legitimately returns
        # other employers' jobs.
        reported = (mapped.get("company") or "").strip()
        brand_id = None
        for name, bid in name_to_brand.items():
            if employer_matches(name, reported):
                brand_id = bid
                break
        if not brand_id:
            unmatched += 1
            continue
        if store_snapshot(
            conn, market_id=run["market_id"], brand_id=brand_id,
            source=INDEED_SOURCE, snapshot_type="job_posting",
            provider_item_id=mapped["posting_id"], data=mapped, run_id=run["id"],
        ):
            stored += 1
        else:
            unchanged += 1
    if unmatched:
        logger.info("indeed: %d listing(s) belonged to another employer and "
                    "were dropped", unmatched)
    if provider_errors:
        logger.info("indeed: %d of %d records were provider errors, so this run "
                    "is not evidence that these vendors have no listings",
                    provider_errors, len(records))
    return {"stored": stored, "unchanged": unchanged, "unmatched": unmatched,
            "expired": expired, "provider_errors": provider_errors}


def seed_crunchbase_urls(conn, market_id: int) -> Dict[str, int]:
    """Give each collecting vendor a guessed Crunchbase URL.

    Crunchbase's slug usually matches the company name slugified — measured at
    roughly two in three on this registry. A miss returns a dead page, costs one
    record, and is recorded as unverified so it can be corrected rather than
    silently retried forever.
    """
    from app.services.brightdata_linkedin import crunchbase_url_for

    rows = conn.execute(text("""
        SELECT mb.brand_id, b.name AS slug FROM bw_market_brands mb
        JOIN bw_brands b ON b.id = mb.brand_id
        WHERE mb.market_id = :m AND mb.collection_enabled
          AND mb.role <> 'excluded'
          AND NOT EXISTS (SELECT 1 FROM bw_vendor_identifiers i
                          WHERE i.brand_id = mb.brand_id
                            AND i.kind = 'crunchbase_url' AND i.valid_to IS NULL)
    """), {"m": market_id}).fetchall()
    added = 0
    for brand_id, slug in rows:
        url = crunchbase_url_for(slug)
        conn.execute(text("""
            INSERT INTO bw_vendor_identifiers
                (brand_id, kind, normalized_value, display_value, provenance)
            SELECT :b, 'crunchbase_url', CAST(:u AS TEXT), :u,
                   CAST(:p AS JSONB)
            WHERE NOT EXISTS (
                SELECT 1 FROM bw_vendor_identifiers
                WHERE kind = 'crunchbase_url'
                  AND normalized_value = CAST(:u AS TEXT) AND valid_to IS NULL)
        """), {"b": brand_id, "u": url,
               "p": json.dumps({"source": "slug_guess", "verified": False})})
        added += 1
    return {"seeded": added, "candidates": len(rows)}


def ingest_for_source(conn, *, run: Dict[str, Any],
                      records: List[dict]) -> Dict[str, int]:
    """Route a delivered batch to the right ingest by its run's source.

    One dispatcher so the poll loop, the reconciler and the webhook cannot
    drift apart about what a source means.
    """
    source = run["source"]
    if source == LINKEDIN_POST_SOURCE:
        url_map, names = linkedin_url_map(conn, run["market_id"])
        return ingest_posts(conn, run=run, records=records,
                            url_to_brand=url_map, brand_names=names)
    if source == CRUNCHBASE_SOURCE:
        return ingest_crunchbase(conn, run=run, records=records,
                                 url_to_brand=crunchbase_url_map(conn, run["market_id"]))
    if source == JOBS_SOURCE:
        url_map, _ = linkedin_url_map(conn, run["market_id"])
        return ingest_jobs(conn, run=run, records=records, url_to_brand=url_map)
    if source == PITCHBOOK_SOURCE:
        return ingest_pitchbook(
            conn, run=run, records=records,
            url_to_brand=identifier_url_map(conn, run["market_id"], "pitchbook_url"))
    if source == ZOOMINFO_SOURCE:
        return ingest_zoominfo(
            conn, run=run, records=records,
            url_to_brand=identifier_url_map(conn, run["market_id"], "zoominfo_url"))
    if source == INDEED_SOURCE:
        return ingest_indeed_jobs(conn, run=run, records=records)
    url_map, _ = linkedin_url_map(conn, run["market_id"])
    return ingest_profiles(conn, run=run, records=records, url_to_brand=url_map)
