"""Cross-sectional analysis of a market: what the stored data can honestly say.

Separate from ``market_publish`` on purpose. That module is about outputs — a
dataset, a feed, a brief. This one is about aggregates, and the outputs consume
it rather than the other way round.

Every function returns its own **coverage**: how many vendors or records the
figure rests on, out of how many it could have. A market where 19 of 38 funded
vendors have a Crunchbase reading is not a market with no investor overlap, and
a panel that does not say so invites the reader to conclude the wrong thing.
Coverage is not a footnote here, it is part of the return value, because a
caller that has to remember to ask for it will forget.

Nothing here calls a model or a provider. It reads rows.
"""

import logging
from typing import Any, Dict, List, Optional

from sqlalchemy import text

logger = logging.getLogger(__name__)

ANALYSES = ("formation", "signal_noise", "funding", "hiring",
            "share_of_voice")


# ``bw_article_categories`` holds one row per (article, brand, **category**),
# so a post filed under three categories appears three times. Every count that
# joins through it has to deduplicate on (brand, article) first or it inflates:
# 562 reviewed posts came back as 783 before this was added.
_POST_BRANDS = """
    SELECT DISTINCT bac.brand_id, bac.article_uri
    FROM bw_article_categories bac
"""


def _coverage(measured: int, total: int, unit: str) -> Dict[str, Any]:
    """The honest denominator, in a shape the UI can render without thinking."""
    return {
        "measured": measured,
        "total": total,
        "unit": unit,
        "complete": measured >= total,
        "label": (f"all {total} {unit}" if measured >= total
                  else f"{measured} of {total} {unit}"),
    }


# ---------------------------------------------------------------------------
# 1. Market formation
# ---------------------------------------------------------------------------

def formation(conn, market_id: int) -> Dict[str, Any]:
    """When the vendors were founded, against when they started announcing.

    Two series that only mean something together. Founding years say a category
    appeared; announcement volume says it started competing. On SOC Automation
    the founding years cluster hard in 2023-2026 and the announcements only
    pick up from early 2026, which is the difference between a market existing
    and a market being contested.

    Founded years come from the registry, so they cover the whole market.
    Announcements come from reviewed vendor posts, so they cover only the
    vendors whose LinkedIn page we collect — stated in ``coverage``.
    """
    founded = [dict(r) for r in conn.execute(text("""
        SELECT (mb.baseline->>'founded_year')::int AS year, COUNT(*) AS vendors
        FROM bw_market_brands mb
        WHERE mb.market_id = :m AND mb.role <> 'excluded'
          AND mb.baseline->>'founded_year' ~ '^[0-9]{4}$'
        GROUP BY 1 ORDER BY 1
    """), {"m": market_id}).mappings().all()]

    in_scope, with_year = conn.execute(text("""
        SELECT COUNT(*),
               COUNT(*) FILTER (WHERE baseline->>'founded_year' ~ '^[0-9]{4}$')
        FROM bw_market_brands
        WHERE market_id = :m AND role <> 'excluded'
    """), {"m": market_id}).fetchone()

    # Announcements by month. Only rows with a parseable ISO date — a post with
    # a broken date would otherwise land in whatever month the cast produced.
    announcements = [dict(r) for r in conn.execute(text("""
        SELECT TO_CHAR(DATE_TRUNC('month', a.publication_date::timestamp),
                       'YYYY-MM') AS month,
               COUNT(*) FILTER (WHERE ma.review_verdict = 'signal') AS signal,
               COUNT(*) FILTER (WHERE ma.review_verdict = 'commentary')
                   AS commentary,
               COUNT(*) AS posts
        FROM bw_market_articles ma
        JOIN articles a ON a.uri = ma.article_uri
        WHERE ma.market_id = :m AND ma.review_verdict IS NOT NULL
          AND a.publication_date ~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}'
        GROUP BY 1 ORDER BY 1
    """), {"m": market_id}).mappings().all()]

    posting_vendors, reviewed = conn.execute(text(f"""
        WITH pb AS ({_POST_BRANDS})
        SELECT COUNT(DISTINCT pb.brand_id), COUNT(DISTINCT ma.article_uri)
        FROM bw_market_articles ma
        JOIN pb ON pb.article_uri = ma.article_uri
        WHERE ma.market_id = :m AND ma.review_verdict IS NOT NULL
    """), {"m": market_id}).fetchone()

    recent = sum(r["vendors"] for r in founded if r["year"] and r["year"] >= 2023)

    return {
        "founded_by_year": founded,
        "announcements_by_month": announcements,
        "founded_since_2023": recent,
        "vendors_in_scope": in_scope or 0,
        "reviewed_posts": reviewed or 0,
        "coverage": _coverage(with_year or 0, in_scope or 0,
                              "vendors have a founding year"),
        "announcement_coverage": _coverage(
            posting_vendors or 0, in_scope or 0, "vendors post on LinkedIn"),
    }


# ---------------------------------------------------------------------------
# 2. Signal to noise
# ---------------------------------------------------------------------------

# Below this a ratio is arithmetic on too little to mean anything. A vendor
# with two posts, both announcements, is not "the most substantive vendor in
# the market".
MIN_POSTS_FOR_RATIO = 8


def signal_noise(conn, market_id: int) -> Dict[str, Any]:
    """Which vendors announce things, and which just post.

    Counts of the three review verdicts per vendor. ``signal_share`` is the
    fraction of a vendor's posts that state a fact, and is only computed above
    ``MIN_POSTS_FOR_RATIO`` — a ratio over three posts sorts to the top of any
    league table and means nothing.
    """
    rows = [dict(r) for r in conn.execute(text(f"""
        WITH pb AS ({_POST_BRANDS})
        SELECT b.id AS brand_id, b.display_name AS vendor,
               COUNT(*) FILTER (WHERE ma.review_verdict = 'signal') AS signal,
               COUNT(*) FILTER (WHERE ma.review_verdict = 'commentary')
                   AS commentary,
               COUNT(*) FILTER (WHERE ma.review_verdict = 'noise') AS noise,
               COUNT(*) AS posts
        FROM bw_market_articles ma
        JOIN pb ON pb.article_uri = ma.article_uri
        JOIN bw_brands b ON b.id = pb.brand_id
        JOIN bw_market_brands mb ON mb.brand_id = b.id AND mb.market_id = :m
        WHERE ma.market_id = :m AND ma.review_verdict IS NOT NULL
        GROUP BY 1, 2
        ORDER BY signal DESC, posts DESC
    """), {"m": market_id}).mappings().all()]

    for row in rows:
        row["signal_share"] = (round(row["signal"] / row["posts"], 3)
                               if row["posts"] >= MIN_POSTS_FOR_RATIO else None)

    kinds = [dict(r) for r in conn.execute(text("""
        SELECT review_kind AS kind, COUNT(*) AS n
        FROM bw_market_articles
        WHERE market_id = :m AND review_verdict = 'signal'
              AND review_kind IS NOT NULL
        GROUP BY 1 ORDER BY n DESC, kind
    """), {"m": market_id}).mappings().all()]

    in_scope = conn.execute(text("""
        SELECT COUNT(*) FROM bw_market_brands
        WHERE market_id = :m AND role <> 'excluded'
    """), {"m": market_id}).scalar() or 0

    return {
        "vendors": rows,
        "signal_kinds": kinds,
        "min_posts_for_ratio": MIN_POSTS_FOR_RATIO,
        "totals": {
            "signal": sum(r["signal"] for r in rows),
            "commentary": sum(r["commentary"] for r in rows),
            "noise": sum(r["noise"] for r in rows),
        },
        "coverage": _coverage(len(rows), in_scope,
                              "vendors have posts we have read"),
    }


# ---------------------------------------------------------------------------
# 3. Funding and momentum
# ---------------------------------------------------------------------------

def funding(conn, market_id: int) -> Dict[str, Any]:
    """Stage mix, momentum, and which investors appear more than once.

    All three read the latest ``funding`` snapshot per vendor, which is a
    Crunchbase record. Coverage matters more here than anywhere else: an
    investor appears to back one vendor when we have only read half the
    market's Crunchbase pages, and a reader who does not know that will read a
    fragmented market where there may be a concentrated one.
    """
    latest = """
        SELECT DISTINCT ON (s.brand_id) s.brand_id, s.data, b.display_name
        FROM bw_vendor_snapshots s
        JOIN bw_market_brands mb ON mb.brand_id = s.brand_id
                                 AND mb.market_id = :m AND mb.role <> 'excluded'
        JOIN bw_brands b ON b.id = s.brand_id
        WHERE s.snapshot_type = 'funding'
        ORDER BY s.brand_id, s.observed_at DESC
    """

    stages = [dict(r) for r in conn.execute(text(f"""
        WITH latest AS ({latest})
        SELECT COALESCE(NULLIF(data->>'last_funding_type', ''), 'not stated')
                   AS stage,
               COUNT(*) AS vendors
        FROM latest GROUP BY 1 ORDER BY vendors DESC, stage
    """), {"m": market_id}).mappings().all()]

    momentum = [dict(r) for r in conn.execute(text(f"""
        WITH latest AS ({latest})
        SELECT brand_id, display_name AS vendor,
               (data->>'growth_score')::numeric AS growth_score,
               (data->>'heat_score')::numeric AS heat_score,
               data->>'growth_trend' AS growth_trend,
               data->>'heat_trend' AS heat_trend,
               (data->>'cb_rank')::numeric AS cb_rank,
               (data->>'num_funding_rounds')::numeric AS rounds
        FROM latest
        WHERE data->>'growth_score' IS NOT NULL
           OR data->>'heat_score' IS NOT NULL
        ORDER BY heat_score DESC NULLS LAST
    """), {"m": market_id}).mappings().all()]
    for row in momentum:
        for key in ("growth_score", "heat_score", "cb_rank", "rounds"):
            if row[key] is not None:
                row[key] = float(row[key])

    investors = [dict(r) for r in conn.execute(text(f"""
        WITH latest AS ({latest})
        SELECT inv AS investor,
               COUNT(DISTINCT brand_id) AS vendors,
               ARRAY_AGG(DISTINCT display_name ORDER BY display_name) AS backing
        FROM latest, JSONB_ARRAY_ELEMENTS_TEXT(
            CASE WHEN JSONB_TYPEOF(data->'investors') = 'array'
                 THEN data->'investors' ELSE '[]'::jsonb END) AS inv
        GROUP BY 1 HAVING COUNT(DISTINCT brand_id) > 1
        ORDER BY vendors DESC, investor
        LIMIT 25
    """), {"m": market_id}).mappings().all()]

    read, with_url = conn.execute(text("""
        SELECT (SELECT COUNT(DISTINCT s.brand_id)
                  FROM bw_vendor_snapshots s
                  JOIN bw_market_brands mb ON mb.brand_id = s.brand_id
                                           AND mb.market_id = :m
                 WHERE s.snapshot_type = 'funding'),
               (SELECT COUNT(DISTINCT i.brand_id)
                  FROM bw_vendor_identifiers i
                  JOIN bw_market_brands mb ON mb.brand_id = i.brand_id
                                           AND mb.market_id = :m
                 WHERE i.kind = 'crunchbase_url' AND i.valid_to IS NULL)
    """), {"m": market_id}).fetchone()

    return {
        "stages": stages,
        "momentum": momentum,
        "shared_investors": investors,
        "coverage": _coverage(read or 0, with_url or 0,
                              "vendors with a Crunchbase page have been read"),
    }


# ---------------------------------------------------------------------------
# 4. Hiring posture
# ---------------------------------------------------------------------------

# Job functions collapse into these. LinkedIn's own labels are inconsistent —
# "Information Technology" and "Engineering and Information Technology" are the
# same thing for this purpose — and leaving them apart splits a small sample
# into an unreadable one.
_FUNCTION_GROUPS = (
    ("engineering", ("engineering", "information technology", "research")),
    ("sales", ("sales", "business development")),
    ("marketing", ("marketing", "product management")),
    ("operations", ("management", "manufacturing", "administrative",
                    "human resources", "finance")),
)


def _group_function(label: Optional[str]) -> str:
    text_label = (label or "").strip().lower()
    if not text_label:
        return "not stated"
    for name, needles in _FUNCTION_GROUPS:
        if any(n in text_label for n in needles):
            return name
    return "other"


# Job locations arrive as free text — "Tel Aviv District, Israel", "Paris,
# Île-de-France, France", or bare "United States". The country is the last
# comma-separated part, which holds for every shape seen so far, and anything
# unrecognised keeps its own text rather than being bucketed into "other".
_REGIONS = {
    "united states": "North America", "usa": "North America",
    "canada": "North America", "mexico": "North America",
    "united kingdom": "Europe", "ireland": "Europe", "france": "Europe",
    "germany": "Europe", "spain": "Europe", "netherlands": "Europe",
    "italy": "Europe", "poland": "Europe", "sweden": "Europe",
    "switzerland": "Europe", "portugal": "Europe", "belgium": "Europe",
    "israel": "Middle East", "united arab emirates": "Middle East",
    "saudi arabia": "Middle East", "qatar": "Middle East",
    "india": "Asia Pacific", "singapore": "Asia Pacific",
    "australia": "Asia Pacific", "japan": "Asia Pacific",
    "remote": "Remote",
}


# US postings often stop at the state — "Boston, MA", "McLean, VA" — with no
# country at all, so the last comma-separated part is a state code and taking
# it as the country produced a region called "MA".
_US_STATES = {
    "al", "ak", "az", "ar", "ca", "co", "ct", "de", "fl", "ga", "hi", "id",
    "il", "in", "ia", "ks", "ky", "la", "me", "md", "ma", "mi", "mn", "ms",
    "mo", "mt", "ne", "nv", "nh", "nj", "nm", "ny", "nc", "nd", "oh", "ok",
    "or", "pa", "ri", "sc", "sd", "tn", "tx", "ut", "vt", "va", "wa", "wv",
    "wi", "wy", "dc",
}


def _country_of(location: Optional[str]) -> str:
    text_value = (location or "").strip()
    if not text_value:
        return "not stated"
    tail = text_value.split(",")[-1].strip()
    if tail.lower() in _US_STATES:
        return "United States"
    return tail or "not stated"


def _region_of(country: str) -> str:
    return _REGIONS.get(country.strip().lower(), country or "not stated")


def hiring(conn, market_id: int) -> Dict[str, Any]:
    """What the market is hiring for, grouped and per vendor.

    Engineering-heavy against sales-heavy hiring is the cheapest read available
    on whether a vendor is still building or has started selling. It is also
    the thinnest analysis here — job listings exist for a handful of vendors —
    so the coverage figure is the first thing a reader should see.
    """
    rows = [dict(r) for r in conn.execute(text("""
        SELECT DISTINCT ON (s.provider_item_id)
               b.id AS brand_id, b.display_name AS vendor,
               s.data->>'function' AS function,
               s.data->>'seniority' AS seniority,
               s.data->>'employment_type' AS employment_type,
               s.data->>'location' AS location
        FROM bw_vendor_snapshots s
        JOIN bw_market_brands mb ON mb.brand_id = s.brand_id
                                 AND mb.market_id = :m AND mb.role <> 'excluded'
        JOIN bw_brands b ON b.id = s.brand_id
        WHERE s.snapshot_type = 'job_posting'
        ORDER BY s.provider_item_id, s.observed_at DESC
    """), {"m": market_id}).mappings().all()]

    by_function: Dict[str, int] = {}
    by_seniority: Dict[str, int] = {}
    by_country: Dict[str, int] = {}
    by_region: Dict[str, int] = {}
    # Function against region, which is the cross-cut that says something:
    # engineering in one place and sales in another is a company expanding, not
    # a company hiring.
    function_by_region: Dict[str, Dict[str, int]] = {}
    per_vendor: Dict[int, Dict[str, Any]] = {}
    for row in rows:
        group = _group_function(row["function"])
        by_function[group] = by_function.get(group, 0) + 1
        level = (row["seniority"] or "not stated").strip() or "not stated"
        by_seniority[level] = by_seniority.get(level, 0) + 1
        country = _country_of(row.get("location"))
        region = _region_of(country)
        by_country[country] = by_country.get(country, 0) + 1
        by_region[region] = by_region.get(region, 0) + 1
        function_by_region.setdefault(region, {})
        function_by_region[region][group] = \
            function_by_region[region].get(group, 0) + 1
        entry = per_vendor.setdefault(row["brand_id"], {
            "brand_id": row["brand_id"], "vendor": row["vendor"],
            "openings": 0, "engineering": 0, "sales": 0,
        })
        entry["openings"] += 1
        if group in ("engineering", "sales"):
            entry[group] += 1

    in_scope = conn.execute(text("""
        SELECT COUNT(*) FROM bw_market_brands
        WHERE market_id = :m AND role <> 'excluded'
    """), {"m": market_id}).scalar() or 0

    return {
        "openings": len(rows),
        "by_function": [{"function": k, "openings": v}
                        for k, v in sorted(by_function.items(),
                                           key=lambda kv: -kv[1])],
        "by_seniority": [{"seniority": k, "openings": v}
                         for k, v in sorted(by_seniority.items(),
                                            key=lambda kv: -kv[1])],
        "by_country": [{"country": k, "openings": v}
                       for k, v in sorted(by_country.items(),
                                          key=lambda kv: -kv[1])],
        "by_region": [{"region": k, "openings": v}
                      for k, v in sorted(by_region.items(),
                                         key=lambda kv: -kv[1])],
        "function_by_region": [
            {"region": region, **counts}
            for region, counts in sorted(function_by_region.items(),
                                         key=lambda kv: -sum(kv[1].values()))],
        "by_vendor": sorted(per_vendor.values(),
                            key=lambda v: -v["openings"]),
        "coverage": _coverage(len(per_vendor), in_scope,
                              "vendors have job listings we have seen"),
    }


def run(conn, market_id: int, name: str) -> Dict[str, Any]:
    """Dispatch by name. Raises ValueError on an unknown analysis."""
    fn = {"formation": formation, "signal_noise": signal_noise,
          "funding": funding, "hiring": hiring,
          "share_of_voice": share_of_voice}.get(name)
    if not fn:
        raise ValueError(f"unknown analysis: {name}")
    return fn(conn, market_id)


# ---------------------------------------------------------------------------
# Drilldown — the vendors behind a number
# ---------------------------------------------------------------------------
#
# Every figure on the overview was a dead end. "62 vendors with no signal" is
# the most interesting number on that page and there was no way to see which
# 62. These are the sets behind the figures, named so a link can carry one.

DRILLDOWNS = ("quiet", "watched", "paused", "observed", "unobserved",
              "disclosed", "undisclosed", "no_linkedin", "posting", "hiring")


def drilldown(conn, market_id: int, name: str) -> Dict[str, Any]:
    """The vendors behind one overview figure.

    Returns the same shape whatever the filter, so the UI renders one table.
    """
    where = {
        "quiet": """NOT EXISTS (SELECT 1 FROM bw_article_categories bac
                                WHERE bac.brand_id = b.id)
                    AND NOT EXISTS (SELECT 1 FROM bw_vendor_snapshots s
                                    WHERE s.brand_id = b.id
                                      AND s.snapshot_type = 'job_posting')""",
        "watched": "mb.collection_enabled",
        "paused": "NOT mb.collection_enabled",
        "observed": """EXISTS (SELECT 1 FROM bw_vendor_snapshots s
                               WHERE s.brand_id = b.id)""",
        "unobserved": """NOT EXISTS (SELECT 1 FROM bw_vendor_snapshots s
                                     WHERE s.brand_id = b.id)""",
        "disclosed":
            "mb.baseline->'funding_baseline'->>'status' = 'Disclosed'",
        "undisclosed":
            "COALESCE(mb.baseline->'funding_baseline'->>'status','') "
            "<> 'Disclosed'",
        "no_linkedin": """NOT EXISTS (SELECT 1 FROM bw_vendor_identifiers i
                                      WHERE i.brand_id = b.id
                                        AND i.kind = 'linkedin_company_url'
                                        AND i.valid_to IS NULL)""",
        "posting": """EXISTS (SELECT 1 FROM bw_market_articles ma
                              JOIN bw_article_categories bac
                                   ON bac.article_uri = ma.article_uri
                              WHERE bac.brand_id = b.id
                                AND ma.review_verdict = 'signal')""",
        "hiring": """EXISTS (SELECT 1 FROM bw_vendor_snapshots s
                             WHERE s.brand_id = b.id
                               AND s.snapshot_type = 'job_posting')""",
    }.get(name)
    if not where:
        raise ValueError(f"unknown drilldown: {name}")

    rows = [dict(r) for r in conn.execute(text(f"""
        SELECT b.id AS brand_id, b.display_name AS vendor,
               mb.role, mb.collection_enabled,
               mb.baseline->>'hq_country' AS country,
               mb.baseline->>'founded_year' AS founded,
               mb.baseline->'funding_baseline'->>'status' AS funding_status,
               (mb.baseline->'funding_baseline'->>'total_musd')::numeric AS musd,
               (mb.baseline->'metrics'->>'employee_count')::numeric AS staff,
               (SELECT COUNT(DISTINCT ma.article_uri)
                  FROM bw_market_articles ma
                  JOIN bw_article_categories bac
                       ON bac.article_uri = ma.article_uri
                 WHERE bac.brand_id = b.id
                   AND ma.review_verdict = 'signal') AS announcements,
               (SELECT COUNT(*) FROM bw_vendor_snapshots s
                 WHERE s.brand_id = b.id
                   AND s.snapshot_type = 'job_posting') AS openings
        FROM bw_market_brands mb
        JOIN bw_brands b ON b.id = mb.brand_id
        WHERE mb.market_id = :m AND mb.role <> 'excluded' AND ({where})
        ORDER BY b.display_name
    """), {"m": market_id}).mappings().all()]
    for row in rows:
        for key in ("musd", "staff"):
            if row[key] is not None:
                row[key] = float(row[key])

    return {"drilldown": name, "vendors": rows, "count": len(rows)}


def job_postings(conn, market_id: int,
                 brand_id: Optional[int] = None) -> List[Dict[str, Any]]:
    """The job listings themselves, with their URLs.

    The hiring analysis counts openings and the vendor page counts them again,
    and neither offered a way to read one. Every posting carries a LinkedIn URL
    and always did — the count was the only thing ever surfaced.
    """
    where = ["s.snapshot_type = 'job_posting'", "mb.market_id = :m"]
    params: Dict[str, Any] = {"m": market_id}
    if brand_id is not None:
        where.append("s.brand_id = :b")
        params["b"] = brand_id

    rows = [dict(r) for r in conn.execute(text(f"""
        SELECT DISTINCT ON (s.provider_item_id)
               s.brand_id, b.display_name AS vendor,
               s.data->>'title' AS title,
               s.data->>'location' AS location,
               s.data->>'seniority' AS seniority,
               s.data->>'function' AS function,
               s.data->>'employment_type' AS employment_type,
               s.data->>'posted_date' AS posted_date,
               s.data->>'url' AS url,
               s.observed_at
        FROM bw_vendor_snapshots s
        JOIN bw_market_brands mb ON mb.brand_id = s.brand_id
        JOIN bw_brands b ON b.id = s.brand_id
        WHERE {' AND '.join(where)}
        ORDER BY s.provider_item_id, s.observed_at DESC
    """), params).mappings().all()]

    for row in rows:
        row["function_group"] = _group_function(row.get("function"))
    rows.sort(key=lambda r: (r["vendor"], r["title"] or ""))
    return rows


# ---------------------------------------------------------------------------
# 5. Share of voice
# ---------------------------------------------------------------------------
#
# Who the market is talking about, and who is doing the talking. Two different
# questions that are easy to conflate:
#
#   share of voice — how much of the market's coverage mentions a vendor,
#                    counted separately for what the vendor said about itself
#                    and what everyone else said about it. Collapsing those
#                    lets a vendor buy its way up the table by posting.
#   top voice      — the accounts driving the conversation, which are mostly
#                    not vendors at all.

def share_of_voice(conn, market_id: int, days: Optional[int] = None
                   ) -> Dict[str, Any]:
    """Coverage per vendor, split by who produced it."""
    window = ""
    params: Dict[str, Any] = {"m": market_id}
    if days:
        window = ("AND COALESCE(a.publication_date, a.submission_date) >= :since")
        params["since"] = _iso_days_ago(days)

    rows = [dict(r) for r in conn.execute(text(f"""
        WITH pb AS ({_POST_BRANDS})
        SELECT b.id AS brand_id, b.display_name AS vendor,
               COUNT(DISTINCT a.uri) FILTER (
                   WHERE COALESCE(a.bias_source,'') = 'vendor:linkedin') AS own_posts,
               COUNT(DISTINCT a.uri) FILTER (
                   WHERE COALESCE(a.bias_source,'') <> 'vendor:linkedin') AS earned,
               COUNT(DISTINCT a.uri) AS total
        FROM pb
        JOIN articles a ON a.uri = pb.article_uri
        JOIN bw_brands b ON b.id = pb.brand_id
        JOIN bw_market_brands mb ON mb.brand_id = b.id AND mb.market_id = :m
                                 AND mb.role <> 'excluded'
        WHERE TRUE {window}
        GROUP BY 1, 2
        ORDER BY earned DESC, total DESC
    """), params).mappings().all()]

    earned_total = sum(r["earned"] for r in rows) or 0
    own_total = sum(r["own_posts"] for r in rows) or 0
    for row in rows:
        # Share of *earned* coverage, not of everything. A vendor that posts a
        # hundred times has a hundred posts, not a hundred mentions.
        row["earned_share"] = (round(row["earned"] / earned_total, 4)
                               if earned_total else None)
        row["own_share"] = (round(row["own_posts"] / own_total, 4)
                            if own_total else None)

    in_scope = conn.execute(text("""
        SELECT COUNT(*) FROM bw_market_brands
        WHERE market_id = :m AND role <> 'excluded'
    """), {"m": market_id}).scalar() or 0

    return {
        "vendors": rows,
        "earned_total": earned_total,
        "own_total": own_total,
        "silent": sum(1 for r in rows if r["total"] == 0),
        "days": days,
        "coverage": _coverage(len([r for r in rows if r["total"]]), in_scope,
                              "vendors appear in any coverage"),
    }


def top_voices(conn, market_id: int, days: Optional[int] = None,
               limit: int = 25) -> Dict[str, Any]:
    """The accounts posting about this market, vendor and otherwise.

    Read from ``articles.social_meta``, which carries the author for a
    practitioner post. A vendor's own LinkedIn post has no author of this kind
    — it is the company account — so those are counted separately rather than
    ranked against individuals.
    """
    window = ""
    params: Dict[str, Any] = {"m": market_id, "lim": limit}
    if days:
        window = "AND COALESCE(a.publication_date, a.submission_date) >= :since"
        params["since"] = _iso_days_ago(days)

    voices = [dict(r) for r in conn.execute(text(f"""
        SELECT a.social_meta->>'author' AS author,
               COALESCE(a.social_meta->>'platform',
                        SPLIT_PART(a.news_source, ':', 2),
                        a.news_source) AS platform,
               COUNT(*) AS posts,
               SUM(COALESCE((a.social_meta->>'likes')::numeric, 0)) AS likes,
               SUM(COALESCE((a.social_meta->>'comments')::numeric, 0)) AS comments,
               SUM(COALESCE((a.social_meta->>'reposts')::numeric,
                            (a.social_meta->>'shares')::numeric, 0)) AS reposts,
               MAX(COALESCE(a.publication_date, a.submission_date)) AS last_seen
        FROM bw_market_articles ma
        JOIN articles a ON a.uri = ma.article_uri
        WHERE ma.market_id = :m
          AND a.social_meta IS NOT NULL
          AND a.social_meta->>'author' IS NOT NULL
          AND COALESCE(a.bias_source, '') <> 'vendor:linkedin'
          {window}
        GROUP BY 1, 2
        ORDER BY posts DESC, likes DESC
        LIMIT :lim
    """), params).mappings().all()]
    for v in voices:
        for key in ("likes", "comments", "reposts"):
            v[key] = int(v[key] or 0)
        v["engagement"] = v["likes"] + v["comments"] + v["reposts"]

    total, with_author = conn.execute(text(f"""
        SELECT COUNT(*), COUNT(a.social_meta->>'author')
        FROM bw_market_articles ma
        JOIN articles a ON a.uri = ma.article_uri
        WHERE ma.market_id = :m
          AND COALESCE(a.bias_source, '') <> 'vendor:linkedin'
          AND (a.news_source = 'bluesky' OR a.news_source LIKE 'xpoz%')
          {window}
    """), params).fetchone()

    return {
        "voices": voices,
        "days": days,
        "coverage": _coverage(with_author or 0, total or 0,
                              "practitioner posts name an author"),
    }


def channel_mix(conn, market_id: int, days: Optional[int] = None
                ) -> Dict[str, Any]:
    """How the market's coverage splits across kinds of source, over time."""
    from app.services import market_corpus as mcorp

    rows = mcorp.articles(conn, market_id, limit=20000, days=days,
                          require_signal_for_social=False)
    by_class: Dict[str, int] = {}
    by_month: Dict[str, Dict[str, int]] = {}
    for row in rows:
        kind = row["article_class"]
        by_class[kind] = by_class.get(kind, 0) + 1
        month = (row.get("published") or "")[:7]
        if len(month) == 7:
            by_month.setdefault(month, {})[kind] = \
                by_month.setdefault(month, {}).get(kind, 0) + 1

    series = [{"month": m, **counts} for m, counts in sorted(by_month.items())]
    return {
        "by_class": [{"kind": k, "articles": v}
                     for k, v in sorted(by_class.items(), key=lambda kv: -kv[1])],
        "by_month": series,
        "total": len(rows),
        "days": days,
    }
