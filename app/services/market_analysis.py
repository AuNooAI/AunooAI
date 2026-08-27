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
import os
import re
from typing import Any, Dict, List, Optional

from sqlalchemy import text

from app.services.market_corpus import _iso_days_ago

from app.services import entity_flags
from app.services import market_metrics as mm
from app.services.market_corpus import (earned_sql, own_voice_sql,
                                        vendor_domain_sql)

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


def signal_noise(conn, market_id: int, *, days: Optional[int] = None
                 ) -> Dict[str, Any]:
    """Which vendors announce things, and which just post.

    Counts of the three review verdicts per vendor. ``signal_share`` is the
    fraction of a vendor's posts that state a fact, and is only computed above
    ``MIN_POSTS_FOR_RATIO`` — a ratio over three posts sorts to the top of any
    league table and means nothing.
    """
    window = ""
    params: Dict[str, Any] = {"m": market_id}
    if days:
        window = "AND COALESCE(a.publication_date, a.submission_date) >= :since"
        params["since"] = _iso_days_ago(days)

    rows = [dict(r) for r in conn.execute(text(f"""
        WITH pb AS ({_POST_BRANDS})
        SELECT b.id AS brand_id, b.display_name AS vendor,
               COUNT(*) FILTER (WHERE ma.review_verdict = 'signal') AS signal,
               COUNT(*) FILTER (WHERE ma.review_verdict = 'commentary')
                   AS commentary,
               COUNT(*) FILTER (WHERE ma.review_verdict = 'noise') AS noise,
               COUNT(*) AS posts
        FROM bw_market_articles ma
        JOIN articles a ON a.uri = ma.article_uri
        JOIN pb ON pb.article_uri = ma.article_uri
        JOIN bw_brands b ON b.id = pb.brand_id
        JOIN bw_market_brands mb ON mb.brand_id = b.id AND mb.market_id = :m
        WHERE ma.market_id = :m AND ma.review_verdict IS NOT NULL
              {window}
        GROUP BY 1, 2
        ORDER BY signal DESC, posts DESC
    """), params).mappings().all()]

    for row in rows:
        row["signal_share"] = (round(row["signal"] / row["posts"], 3)
                               if row["posts"] >= MIN_POSTS_FOR_RATIO else None)

    kinds = [dict(r) for r in conn.execute(text(f"""
        SELECT ma.review_kind AS kind, COUNT(*) AS n
        FROM bw_market_articles ma
        JOIN articles a ON a.uri = ma.article_uri
        WHERE ma.market_id = :m AND ma.review_verdict = 'signal'
              AND ma.review_kind IS NOT NULL
              {window}
        GROUP BY 1 ORDER BY n DESC, kind
    """), params).mappings().all()]

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

# Crunchbase's last_funding_type values, in round-progression order, so the
# stage-mix chart reads seed -> growth -> exit instead of by vendor count.
_FUNDING_STAGE_ORDER = [
    "pre_seed", "seed", "series_a", "series_b", "series_c", "series_d",
    "series_e", "series_f", "series_g", "series_h", "series_unknown",
    "corporate_round", "convertible_note", "debt_financing",
    "equity_crowdfunding", "non_equity_assistance", "grant",
    "private_equity", "secondary_market", "post_ipo_equity",
    "post_ipo_debt", "post_ipo_secondary", "funding_round",
    "initial_coin_offering", "undisclosed", "ipo",
]


def _funding_stage_sort_key(stage: str):
    """Known stages in round order; anything unseen (incl. 'not stated') last."""
    try:
        return (0, _FUNDING_STAGE_ORDER.index(stage))
    except ValueError:
        return (1, stage)


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
        FROM latest GROUP BY 1
    """), {"m": market_id}).mappings().all()]
    stages.sort(key=lambda r: _funding_stage_sort_key(r["stage"]))

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

    mom = funding_momentum(conn, market_id)

    return {
        "stages": stages,
        "momentum": momentum,
        "shared_investors": investors,
        "by_month": mom["by_month"],
        "momentum_events": mom["momentum_events"],
        "coverage": _coverage(read or 0, with_url or 0,
                              "vendors with a Crunchbase page have been read"),
    }


def funding_momentum(conn, market_id: int, *, months: int = 12) -> Dict[str, Any]:
    """Market-wide funding-score history: a monthly as-of level, and real moves.

    growth_score/heat_score/cb_rank are Crunchbase's own point-in-time
    scores, read at most weekly (app/tasks/market_monitor.py) and only
    written as a new snapshot row when the value actually changed. by_month
    is therefore a step function (last-observation-carried-forward, same
    approach as market_publish.headcount_trend) — label it "as of" in the
    UI, not "trend": most months repeat the prior reading, since PitchBook
    and ZoomInfo (snapshot_type='firmographic') are manual-only and never
    contribute here. momentum_events is where the real signal is: only the
    vendor snapshots where a score genuinely moved from the one before it.
    """
    # bw_vendor_snapshots cannot predate bw_market_brands, which is created
    # with the market — see market_publish.headcount_trend for the same fix
    # and the reasoning. Without this, a young market's by_month asks for
    # months that structurally could never have a reading.
    market_created = conn.execute(text(
        "SELECT created_at FROM bw_markets WHERE id = :m"),
        {"m": market_id}).scalar() or "1970-01-01"
    by_month = [dict(r) for r in conn.execute(text("""
        WITH months AS (
            SELECT generate_series(
                GREATEST(date_trunc('month', now() - (:months || ' months')::interval),
                         date_trunc('month', CAST(:market_created AS timestamptz))),
                date_trunc('month', now()), '1 month'::interval) AS month_start
        ),
        vendors AS (
            SELECT b.id AS brand_id
            FROM bw_market_brands mb JOIN bw_brands b ON b.id = mb.brand_id
            WHERE mb.market_id = :m AND mb.role <> 'excluded'
        ),
        asof AS (
            SELECT mo.month_start, v.brand_id, s.growth_score, s.heat_score, s.cb_rank
            FROM months mo CROSS JOIN vendors v
            LEFT JOIN LATERAL (
                SELECT (data->>'growth_score')::numeric AS growth_score,
                       (data->>'heat_score')::numeric AS heat_score,
                       (data->>'cb_rank')::numeric AS cb_rank
                FROM bw_vendor_snapshots
                WHERE brand_id = v.brand_id AND snapshot_type = 'funding'
                  AND observed_at <= mo.month_start + interval '1 month'
                ORDER BY observed_at DESC LIMIT 1
            ) s ON TRUE
        )
        SELECT TO_CHAR(month_start, 'YYYY-MM-DD') AS month,
               COUNT(*) FILTER (WHERE heat_score IS NOT NULL) AS n_vendors,
               AVG(heat_score) AS avg_heat_score,
               AVG(growth_score) AS avg_growth_score,
               AVG(cb_rank) AS avg_cb_rank
        FROM asof GROUP BY month_start ORDER BY month_start
    """), {"m": market_id, "months": months,
           "market_created": market_created}).mappings().all()]
    for row in by_month:
        for key in ("avg_heat_score", "avg_growth_score", "avg_cb_rank"):
            row[key] = round(float(row[key]), 1) if row[key] is not None else None

    momentum_events = [dict(r) for r in conn.execute(text("""
        WITH ordered AS (
            SELECT s.brand_id, b.display_name AS vendor, s.observed_at,
                   (s.data->>'heat_score')::numeric AS heat_score,
                   (s.data->>'growth_score')::numeric AS growth_score,
                   LAG((s.data->>'heat_score')::numeric) OVER w AS prev_heat,
                   LAG((s.data->>'growth_score')::numeric) OVER w AS prev_growth,
                   LAG(s.observed_at) OVER w AS prev_observed_at
            FROM bw_vendor_snapshots s
            JOIN bw_market_brands mb ON mb.brand_id = s.brand_id
                                     AND mb.market_id = :m AND mb.role <> 'excluded'
            JOIN bw_brands b ON b.id = s.brand_id
            WHERE s.snapshot_type = 'funding'
            WINDOW w AS (PARTITION BY s.brand_id ORDER BY s.observed_at)
        )
        SELECT vendor, observed_at, prev_observed_at,
               heat_score - prev_heat AS heat_delta,
               growth_score - prev_growth AS growth_delta
        FROM ordered
        WHERE prev_heat IS NOT NULL
          AND (heat_score IS DISTINCT FROM prev_heat
               OR growth_score IS DISTINCT FROM prev_growth)
        ORDER BY observed_at DESC LIMIT 50
    """), {"m": market_id}).mappings().all()]
    for row in momentum_events:
        row["observed_at"] = (row["observed_at"].isoformat()
                               if row["observed_at"] else None)
        row["prev_observed_at"] = (row["prev_observed_at"].isoformat()
                                    if row["prev_observed_at"] else None)
        row["heat_delta"] = (round(float(row["heat_delta"]), 1)
                              if row["heat_delta"] is not None else None)
        row["growth_delta"] = (round(float(row["growth_delta"]), 1)
                                if row["growth_delta"] is not None else None)

    return {"by_month": by_month, "momentum_events": momentum_events}


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


# Job titles carry a location, a seniority and a team in one string —
# "Enterprise Account Executive - Boston", "Sales Engineer - Chicago",
# "Security Analyst - Tier 2". Counting them raw gives a list where every entry
# appears once and nothing can be seen. These patterns reduce a title to the
# role it is, in the order they should be tested: the first match wins, so
# "Sales Engineer" must be checked before the broader "Engineer".
_ROLE_PATTERNS = (
    ("Account Executive", ("account executive", "account exec")),
    ("Sales Engineer", ("sales engineer", "solutions engineer",
                        "solution engineer", "sales development",
                        "channel sales")),
    ("Security Engineer", ("security engineer", "detection engineer")),
    ("Security Analyst", ("security analyst", "soc analyst", "threat analyst")),
    ("Security Researcher", ("security researcher", "threat researcher",
                             "research engineer")),
    ("AI / ML Engineer", ("ai engineer", "ml engineer", "machine learning")),
    ("Software Engineer", ("software engineer", "backend", "frontend",
                           "full stack", "fullstack", "platform engineer",
                           "forward deployed")),
    ("Product Manager", ("product manager", "product management")),
    ("Marketing", ("marketer", "marketing", "demand generation", "content")),
    ("Revenue / Ops", ("revenue operations", "sales operations",
                       "business operations", "legal operations",
                       "operations manager", "finance")),
    ("Customer Success", ("customer success", "solutions architect",
                          "technical account")),
    ("Leadership", ("chief ", "vp ", "vice president", "head of", "director")),
)


def _role_of(title: Optional[str]) -> str:
    """The role a job title describes, with its location and tier removed."""
    text_value = (title or "").strip().lower()
    if not text_value:
        return "not stated"
    for label, needles in _ROLE_PATTERNS:
        if any(n in text_value for n in needles):
            return label
    # Nothing matched. Keep the title's own words up to the first separator,
    # so an unrecognised role reads as itself rather than as "other".
    head = re.split(r"[-–(,]", title.strip())[0].strip()
    return head[:40] or "not stated"


def hiring(conn, market_id: int, *, days: Optional[int] = None) -> Dict[str, Any]:
    """What the market is hiring for, grouped and per vendor.

    Engineering-heavy against sales-heavy hiring is the cheapest read available
    on whether a vendor is still building or has started selling. It is also
    the thinnest analysis here — job listings exist for a handful of vendors —
    so the coverage figure is the first thing a reader should see.

    ``days`` filters to postings last *observed* within the window — the
    closest this snapshot table gets to "opened in this period," since a
    listing has no open date of its own, only repeated observations of it
    still being live.
    """
    window = ""
    params: Dict[str, Any] = {"m": market_id}
    if days:
        window = "AND s.observed_at >= :since"
        params["since"] = _iso_days_ago(days)

    rows = [dict(r) for r in conn.execute(text(f"""
        SELECT DISTINCT ON (s.provider_item_id)
               b.id AS brand_id, b.display_name AS vendor,
               s.source AS source,
               s.data->>'title' AS title,
               s.data->>'function' AS function,
               s.data->>'seniority' AS seniority,
               s.data->>'employment_type' AS employment_type,
               s.data->>'location' AS location
        FROM bw_vendor_snapshots s
        JOIN bw_market_brands mb ON mb.brand_id = s.brand_id
                                 AND mb.market_id = :m AND mb.role <> 'excluded'
        JOIN bw_brands b ON b.id = s.brand_id
        WHERE s.snapshot_type = 'job_posting'
              {window}
        ORDER BY s.provider_item_id, s.observed_at DESC
    """), params).mappings().all()]

    # One role published on both LinkedIn and the company's own board is one
    # role. Both were being counted, so this aggregate said 188 where the
    # drill-down behind it said 149 — and a card that disagrees with its own
    # records is worse than either number alone. The rule lives in
    # market_lists so the two cannot drift apart.
    from app.services.market_lists import drop_cross_source_duplicates
    rows = drop_cross_source_duplicates(rows)

    by_function: Dict[str, int] = {}
    by_role: Dict[str, int] = {}
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
        role = _role_of(row.get("title"))
        by_role[role] = by_role.get(role, 0) + 1
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
            # Every function and role for this vendor, so a row can be expanded
            # rather than only counted.
            "by_function": {}, "by_role": {},
        })
        entry["openings"] += 1
        if group in ("engineering", "sales"):
            entry[group] += 1
        entry["by_function"][group] = entry["by_function"].get(group, 0) + 1
        entry["by_role"][role] = entry["by_role"].get(role, 0) + 1

    in_scope = conn.execute(text("""
        SELECT COUNT(*) FROM bw_market_brands
        WHERE market_id = :m AND role <> 'excluded'
    """), {"m": market_id}).scalar() or 0

    return {
        "openings": len(rows),
        "by_function": [{"function": k, "openings": v}
                        for k, v in sorted(by_function.items(),
                                           key=lambda kv: -kv[1])],
        "by_role": [{"role": k, "openings": v}
                    for k, v in sorted(by_role.items(),
                                       key=lambda kv: (-kv[1], kv[0]))],
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


_DAYS_AWARE = {"signal_noise", "hiring", "share_of_voice"}


def run(conn, market_id: int, name: str, *, days: Optional[int] = None
       ) -> Dict[str, Any]:
    """Dispatch by name. Raises ValueError on an unknown analysis.

    ``days`` only reaches the analyses that have a real "in this period"
    meaning (see ``_DAYS_AWARE``) — formation (founding years) and funding
    (current stage mix, investor overlap) describe the market's present
    state, not activity in a window, so a period filter would not mean
    anything there and is silently ignored.
    """
    fn = {"formation": formation, "signal_noise": signal_noise,
          "funding": funding, "hiring": hiring,
          "share_of_voice": share_of_voice}.get(name)
    if not fn:
        raise ValueError(f"unknown analysis: {name}")
    if name in _DAYS_AWARE:
        return fn(conn, market_id, days=days)
    return fn(conn, market_id)


# ---------------------------------------------------------------------------
# Drilldown — the vendors behind a number
# ---------------------------------------------------------------------------
#
# Every figure on the overview was a dead end. "62 vendors with no signal" is
# the most interesting number on that page and there was no way to see which
# 62. These are the sets behind the figures, named so a link can carry one.

# "The vendor is actually speaking", as SQL. Defined in market_corpus so this
# module and the entity layer cannot drift apart on what an owned post is.
_OWN_VOICE = own_voice_sql("a")


def consistent_voice_min_posts() -> int:
    """Relevant posts before an account counts as a voice rather than a post.

    One post is a post. Ranking a list by engagement and calling it "top
    voices" put 81 single-post accounts of this market's 87 above the one
    account that posted nine times, which inverts the question being asked:
    who is driving this conversation, not which single post did numbers.

    Configurable because three is a judgement, not a measurement.
    """
    try:
        return max(1, int(os.getenv("MARKET_CONSISTENT_VOICE_MIN_POSTS", "3")))
    except ValueError:
        return 3


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
               -- A zero here is a blank cell in the imported workbook, not
               -- a company with no staff, so it reads as unknown. The
               -- observation path already drops these (see
               -- entity_observations._map_workbook_metric); this is the
               -- legacy baseline read catching up.
               NULLIF((mb.baseline->'metrics'->>'employee_count')::numeric, 0)
                   AS staff,
               (SELECT COUNT(DISTINCT ma.article_uri)
                  FROM bw_market_articles ma
                  JOIN bw_article_categories bac
                       ON bac.article_uri = ma.article_uri
                 WHERE bac.brand_id = b.id
                   AND ma.review_verdict = 'signal') AS announcements,
               -- DISTINCT on the provider's own id, to match job_postings()
               -- below. A posting seen twice is one opening; counting rows
               -- made this number drift away from the list it drills into as
               -- soon as a source re-observed anything.
               (SELECT COUNT(DISTINCT s.provider_item_id)
                  FROM bw_vendor_snapshots s
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

# Below this, a vendor's percentage of earned mentions is a percentage of
# almost nothing — 4 of 9 total reads as "44% share of voice" when it is four
# mentions. Same reasoning as MIN_POSTS_FOR_RATIO, sized for the denominator
# here rather than a per-vendor post count.
MIN_EARNED_FOR_SHARE = 20


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
                   WHERE COALESCE(a.bias_source,'') = 'vendor:linkedin'
                     AND {_OWN_VOICE}) AS own_posts,
               -- A reshare counts as neither. It is not the vendor speaking,
               -- and it is not somebody else covering the vendor either, so
               -- adding it to earned would be the same error the other way.
               COUNT(DISTINCT a.uri) FILTER (
                   WHERE COALESCE(a.bias_source,'') = 'vendor:linkedin'
                     AND NOT {_OWN_VOICE}) AS reshared,
               -- A post on the vendor's own site is the vendor speaking, the
               -- same as its LinkedIn. It carries no bias_source, so it used to
               -- fall through to earned: eleven of Dropzone AI's blog posts and
               -- one of Radiant Security's counted as third parties covering
               -- them, which was half this market's earned coverage.
               COUNT(DISTINCT a.uri) FILTER (
                   WHERE COALESCE(a.bias_source,'') <> 'vendor:linkedin'
                     AND {vendor_domain_sql("a", "pb")}) AS owned_web,
               COUNT(DISTINCT a.uri) FILTER (
                   WHERE {earned_sql("a", "pb")}) AS earned,
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

    # Engagement on a vendor's own posts. Volume alone says who shouts most;
    # reactions per post says whether anyone is listening, and the two often
    # disagree — the loudest account in a market is frequently the least heard.
    reach = {r[0]: r for r in conn.execute(text(f"""
        WITH pb AS ({_POST_BRANDS})
        SELECT pb.brand_id,
               SUM(COALESCE((a.social_meta->>'likes')::numeric, 0))
                 + SUM(COALESCE((a.social_meta->>'comments')::numeric, 0))
                 + SUM(COALESCE((a.social_meta->>'reposts')::numeric,
                                (a.social_meta->>'shares')::numeric, 0))
                   AS reactions,
               COUNT(*) FILTER (WHERE a.social_meta IS NOT NULL) AS measured
        FROM pb
        JOIN articles a ON a.uri = pb.article_uri
        WHERE COALESCE(a.bias_source,'') = 'vendor:linkedin'
          AND {_OWN_VOICE} {window}
        GROUP BY 1
    """), params).fetchall()}

    # Earned attention, by channel, from the entity layer's resolved mentions.
    #
    # bw_entity_mentions already holds this — 1,933 rows across 53 brands, with
    # channel and platform kept separate exactly as they should be — and no
    # Market Monitor read path referenced it, while
    # ENTITY_INTELLIGENCE_MENTION_READ was on. So practitioner discussion of a
    # vendor was being resolved and then ignored: `earned` here counts 22
    # articles where the mentions table has 43 across news, Twitter, Bluesky,
    # Reddit and Glassdoor.
    #
    # Added beside `earned` rather than replacing it. `earned` comes from
    # bw_article_categories and existing callers compare against it; a number
    # that silently doubles is worse than two numbers whose sources are stated.
    mentions: Dict[int, Dict[str, Any]] = {}
    if entity_flags.mention_read():
        mwindow = ""
        if days:
            mwindow = ("AND COALESCE(a.publication_date, a.submission_date) "
                       ">= :since")
        for r in conn.execute(text(f"""
            SELECT m.brand_id, m.channel, m.platform,
                   COUNT(DISTINCT m.article_uri) AS items
              FROM bw_entity_mentions m
              JOIN bw_market_brands mb ON mb.brand_id = m.brand_id
                                       AND mb.market_id = :m
              JOIN articles a ON a.uri = m.article_uri
             WHERE mb.role <> 'excluded' {mwindow}
             GROUP BY 1, 2, 3
        """), params).mappings().all():
            # Keyed by (channel, platform) and split afterwards. Aggregating
            # platform independently mixed the vendor's own LinkedIn posts into
            # a platform breakdown labelled earned attention — 72 next to a
            # total of 13, which is not a rounding disagreement, it is two
            # different measures under one heading.
            bucket = mentions.setdefault(int(r["brand_id"]), {})
            key = (r["channel"] or "unknown", r["platform"])
            bucket[key] = bucket.get(key, 0) + int(r["items"])

    earned_total = sum(r["earned"] for r in rows) or 0
    own_total = sum(r["own_posts"] for r in rows) or 0
    # A percentage of a handful of mentions turns noise into a ranking — a
    # vendor with 4 of 9 total mentions reads as "44% share" when it is really
    # "four mentions". reactions_per_post already gated on a per-row minimum;
    # this is the market-wide equivalent for the denominator itself.
    share_reliable = earned_total >= MIN_EARNED_FOR_SHARE
    for row in rows:
        # Owned social is the vendor's own channel and is already counted as
        # own_posts; including it here would double it under a different name.
        # Excluded from both breakdowns, not just the channel one.
        by_channel: Dict[str, int] = {}
        by_platform: Dict[str, int] = {}
        for (channel, platform), items in (
                mentions.get(row["brand_id"]) or {}).items():
            if channel == "owned_social":
                continue
            by_channel[channel] = by_channel.get(channel, 0) + items
            if platform:
                by_platform[platform] = by_platform.get(platform, 0) + items
        row["attention"] = {
            "by_channel": by_channel,
            "by_platform": by_platform,
            "total": sum(by_channel.values()),
        }
        hit = reach.get(row["brand_id"])
        row["reactions"] = int(hit[1] or 0) if hit else 0
        row["measured_posts"] = int(hit[2] or 0) if hit else 0
        # Per-post reach, only where enough posts were measured for an average
        # to mean anything.
        row["reactions_per_post"] = (
            round(row["reactions"] / row["measured_posts"], 1)
            if row["measured_posts"] >= 5 else None)
        # Share of *earned* coverage, not of everything. A vendor that posts a
        # hundred times has a hundred posts, not a hundred mentions.
        row["earned_share"] = (round(row["earned"] / earned_total, 4)
                               if share_reliable else None)
        row["own_share"] = (round(row["own_posts"] / own_total, 4)
                            if own_total else None)

    in_scope = conn.execute(text("""
        SELECT COUNT(*) FROM bw_market_brands
        WHERE market_id = :m AND role <> 'excluded'
    """), {"m": market_id}).scalar() or 0

    # Read once and reused by the quiet/unmeasured split and by the metric
    # block, so the two cannot disagree about whether this source worked.
    post_collection = mm.collection_state(conn, market_id,
                                          'linkedin_company_post')

    loudest = sorted((r for r in rows if r["own_posts"]),
                     key=lambda r: -r["own_posts"])[:10]

    # The actual quiet end of the market: vendors with zero own LinkedIn posts
    # in the window. `rows` only has vendors with at least one article (own or
    # earned) at all — a vendor with none never reaches it — so this reads the
    # full in-scope registry instead of deriving "quietest" from `loudest`
    # (the earlier version was `loudest[-10:]` reversed: the bottom of the top
    # ten, not the vendors that actually say nothing).
    # Silence is only silence if somebody listened. A vendor whose post
    # collection has never succeeded has no posts on file, so the query above
    # returned it as quiet — the dashboard accused 57 companies of saying
    # nothing when nothing had ever been collected from them. Quiet now
    # requires a successful run for that vendor; the rest are reported as
    # unmeasured, which is a different claim and an honest one.
    #
    # The gate is the per-vendor policy row, not the presence of posts. Reading
    # it from content would be circular: no posts is exactly the condition
    # under test.
    quiet_sql = f"""
        SELECT b.id AS brand_id, b.display_name AS vendor,
               p.last_success_at AS collected_at,
               -- All-time, deliberately unbounded by the selected window. A
               -- vendor quiet this month may have posted last month, and
               -- "last posted: never" when it posted in June is a lie the
               -- window would tell.
               (SELECT MAX(COALESCE(a.publication_date, a.submission_date))
                  FROM bw_article_categories bac
                  JOIN articles a ON a.uri = bac.article_uri
                 WHERE bac.brand_id = b.id
                   AND COALESCE(a.bias_source,'') = 'vendor:linkedin'
                   AND {_OWN_VOICE}) AS last_posted_at
        FROM bw_market_brands mb
        JOIN bw_brands b ON b.id = mb.brand_id
        LEFT JOIN bw_entity_source_policies p
               ON p.brand_id = b.id AND p.source = 'linkedin_company_post'
        WHERE mb.market_id = :m AND mb.role <> 'excluded'
          AND NOT EXISTS (
              SELECT 1 FROM bw_article_categories bac
              JOIN articles a ON a.uri = bac.article_uri
              WHERE bac.brand_id = b.id
                AND COALESCE(a.bias_source,'') = 'vendor:linkedin'
                AND {_OWN_VOICE}
                {window}
          )
          AND p.last_success_at IS {{null_test}}
        ORDER BY b.display_name
    """
    quietest = [dict(r) for r in conn.execute(
        text(quiet_sql.format(null_test="NOT NULL")),
        params).mappings().all()]
    # Not quiet and not loud: not measured. Kept as its own list so no caller
    # can accidentally fold it back into the quiet count.
    unmeasured = [dict(r) for r in conn.execute(
        text(quiet_sql.format(null_test="NULL")),
        params).mappings().all()]
    for row in quietest + unmeasured:
        row["posts_in_selected_window"] = 0
    quietest_total = len(quietest)
    unmeasured_total = len(unmeasured)

    return {
        "vendors": rows,
        "loudest": loudest,
        "quietest": quietest,
        "quietest_total": quietest_total,
        # Vendors we cannot describe either way. Separate from quiet by
        # design — see the comment on quiet_sql.
        "unmeasured": unmeasured,
        "unmeasured_total": unmeasured_total,
        "metric": mm.metric(
            "owned_post_volume",
            label="Posts the vendors published themselves",
            definition=(
                "Posts a vendor put out on its own LinkedIn account during the "
                "period. If a vendor reshared somebody else's post, we count "
                "that separately, because resharing is not the same as having "
                "something to say."),
            numerator="posts from the vendors' own LinkedIn accounts",
            denominator="vendors whose posts we managed to collect",
            window={"days": days},
            collection=post_collection,
            value=own_total,
            limitations=[
                "LinkedIn only. A vendor that is busy on another network "
                "will look quieter here than it is.",
                "We only started recording whether a post was a reshare "
                "part-way through. Older posts all count as the vendor's own.",
                "When we say somebody wrote about a vendor, we mean somebody "
                "other than the vendor. A post on the vendor's own site counts "
                "as the vendor talking, not as coverage of it.",
            ]),
        "reactions_total": sum(r["reactions"] for r in rows),
        "earned_total": earned_total,
        "earned_share_reliable": share_reliable,
        "min_earned_for_share": MIN_EARNED_FOR_SHARE,
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

    # Sorted and cut to `limit` by engagement, not post count — "top voices"
    # naming a table ordered by volume let a 9-post, 0-reaction account rank
    # first over a 1-post, 28-reaction one. engagement has to be computed and
    # sorted on here, in SQL, before LIMIT — doing it in Python after the fact
    # would only re-sort whichever `limit` accounts posts DESC happened to cut.
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
               SUM(COALESCE((a.social_meta->>'likes')::numeric, 0))
                 + SUM(COALESCE((a.social_meta->>'comments')::numeric, 0))
                 + SUM(COALESCE((a.social_meta->>'reposts')::numeric,
                                (a.social_meta->>'shares')::numeric, 0))
                   AS engagement,
               MAX(COALESCE(a.publication_date, a.submission_date)) AS last_seen
        FROM bw_market_articles ma
        JOIN articles a ON a.uri = ma.article_uri
        WHERE ma.market_id = :m
          AND a.social_meta IS NOT NULL
          AND a.social_meta->>'author' IS NOT NULL
          AND COALESCE(a.bias_source, '') <> 'vendor:linkedin'
          {window}
        GROUP BY 1, 2
        ORDER BY engagement DESC, posts DESC
        LIMIT :lim
    """), params).mappings().all()]
    for v in voices:
        for key in ("likes", "comments", "reposts"):
            v[key] = int(v[key] or 0)
        v["engagement"] = v["likes"] + v["comments"] + v["reposts"]

    # Who each handle belongs to. Brand monitoring already keeps account
    # profiles in social_accounts — bio, reach, topics, brand-relative
    # sentiment, watchlist state — and Top Voices was listing handles beside
    # them without ever joining the two, so the same account was a stranger
    # here and a profile one screen away.
    #
    # Reports whether a profile exists; does not build one.
    # social_profile_service is explicit that profiles are built "ON-DEMAND
    # only (never bulk/auto) for cost", and this list is 87 accounts.
    # `handle_canonical` is returned so a caller can hand it straight to
    # /accounts/profile, which is keyed on (platform, handle_canonical).
    if voices:
        pairs = {(v["author"], v["platform"]) for v in voices}
        accounts = {
            (r["handle_canonical"], r["platform"]): dict(r)
            for r in conn.execute(text("""
                SELECT platform, handle_canonical, id AS account_id, handle,
                       display_name, followers_count, summary, watchlisted,
                       tags, bio, profile_url,
                       last_profiled_at IS NOT NULL AS profiled
                  FROM social_accounts
                 WHERE (platform, handle_canonical) IN (
                     SELECT lower(p), lower(h) FROM UNNEST(:plats, :handles)
                          AS t(p, h))
            """), {"plats": [p for _, p in pairs],
                   "handles": [a for a, _ in pairs]}).mappings().all()
        }
        for v in voices:
            hit = accounts.get((str(v["author"]).lower(),
                                str(v["platform"]).lower()))
            # Absent is a real answer: an author we have seen posting but never
            # registered as an account. Saying so beats an empty dict that
            # reads as "profiled, and empty".
            v["account"] = ({
                "account_id": hit["account_id"],
                "handle": hit["handle"],
                "handle_canonical": hit["handle_canonical"],
                "display_name": hit["display_name"],
                "followers": hit["followers_count"],
                "summary": hit["summary"],
                "bio": hit["bio"],
                "profile_url": hit["profile_url"],
                "watchlisted": bool(hit["watchlisted"]),
                "tags": hit["tags"] or [],
                "profiled": bool(hit["profiled"]),
            } if hit else None)

    # What each account is actually talking about. A ranked list of handles
    # with no subject is a list of strangers — the useful question is who is
    # driving which conversation, and about whom.
    if voices:
        handles = [v["author"] for v in voices]
        subjects: Dict[str, Dict[str, Any]] = {
            h: {"terms": {}, "vendors": {}} for h in handles}

        for author, term in conn.execute(text(f"""
            SELECT a.social_meta->>'author' AS author, term
            FROM bw_market_articles ma
            JOIN articles a ON a.uri = ma.article_uri,
                 UNNEST(ma.matched_terms) AS term
            WHERE ma.market_id = :m
              AND a.social_meta->>'author' = ANY(:handles)
              {window}
        """), {**params, "handles": handles}).fetchall():
            bucket = subjects.get(author)
            if bucket is not None:
                bucket["terms"][term] = bucket["terms"].get(term, 0) + 1

        for author, vendor in conn.execute(text(f"""
            SELECT a.social_meta->>'author' AS author, b.display_name
            FROM bw_market_articles ma
            JOIN articles a ON a.uri = ma.article_uri
            JOIN bw_article_categories bac ON bac.article_uri = a.uri
            JOIN bw_brands b ON b.id = bac.brand_id
            JOIN bw_market_brands mb ON mb.brand_id = b.id AND mb.market_id = :m
            WHERE ma.market_id = :m
              AND a.social_meta->>'author' = ANY(:handles)
              {window}
        """), {**params, "handles": handles}).fetchall():
            bucket = subjects.get(author)
            if bucket is not None:
                bucket["vendors"][vendor] = bucket["vendors"].get(vendor, 0) + 1

        for v in voices:
            bucket = subjects.get(v["author"], {"terms": {}, "vendors": {}})
            v["terms"] = [{"term": t, "n": n} for t, n in
                          sorted(bucket["terms"].items(),
                                 key=lambda kv: (-kv[1], kv[0]))[:4]]
            v["vendors"] = [{"vendor": t, "n": n} for t, n in
                            sorted(bucket["vendors"].items(),
                                   key=lambda kv: (-kv[1], kv[0]))[:4]]

    total, with_author = conn.execute(text(f"""
        SELECT COUNT(*), COUNT(a.social_meta->>'author')
        FROM bw_market_articles ma
        JOIN articles a ON a.uri = ma.article_uri
        WHERE ma.market_id = :m
          AND COALESCE(a.bias_source, '') <> 'vendor:linkedin'
          AND (a.news_source = 'bluesky' OR a.news_source LIKE 'xpoz%')
          {window}
    """), params).fetchone()

    # Two different questions, split rather than blended. `voices` stays as it
    # was so existing callers keep working; it is the union, still engagement-
    # ranked.
    threshold = consistent_voice_min_posts()
    for v in voices:
        v["sample_of_one"] = int(v["posts"] or 0) <= 1

    # Who is actually driving the conversation: ranked by how much they say
    # first, because that is the claim the word "voice" makes.
    consistent = sorted(
        (v for v in voices if int(v["posts"] or 0) >= threshold),
        key=lambda v: (-int(v["posts"] or 0), -int(v["engagement"] or 0),
                       str(v.get("last_seen") or "")))
    # Individual posts that travelled, including from accounts with only one.
    # Legitimate, and not a voice.
    breakout = [v for v in voices if int(v["posts"] or 0) < threshold]

    return {
        "voices": voices,
        "consistent": consistent,
        "breakout": breakout,
        "consistent_min_posts": threshold,
        "days": days,
        "coverage": _coverage(with_author or 0, total or 0,
                              "practitioner posts name an author"),
    }


# ---------------------------------------------------------------------------
# 6. Leaderboards — per-network rankings, and who joined
# ---------------------------------------------------------------------------

_PLATFORM_EXPR = ("COALESCE(a.social_meta->>'platform', "
                  "SPLIT_PART(a.news_source, ':', 2), a.news_source)")

# How many top entries a per-platform ranking keeps.
LEADERBOARD_LIMIT = 5


def network_leaderboard(conn, market_id: int, *, days: Optional[int] = None
                        ) -> Dict[str, Any]:
    """Per-platform rankings: who's discussed, whose posts spread, what's trending.

    Three different questions, kept separate rather than one blended score:

    - **most_discussed** — earned mentions only. A vendor's own post about
      itself is not evidence anyone else is discussing it; same owned/earned
      split ``share_of_voice()`` already draws, applied per platform.
    - **most_shared** / **top_posts** — any post, owned or earned. Virality
      does not care who posted it, and a vendor's own post going viral is
      itself the finding.

    LinkedIn is almost entirely vendor company posts in this schema (posts
    from practitioners rarely carry ``bias_source = 'vendor:linkedin'`` set
    to false there), so it can be strong on most_shared/top_posts and nearly
    empty on most_discussed — that split is real, not a bug.
    """
    window = ""
    params: Dict[str, Any] = {"m": market_id}
    if days:
        window = "AND COALESCE(a.publication_date, a.submission_date) >= :since"
        params["since"] = _iso_days_ago(days)

    discussed_rows = conn.execute(text(f"""
        WITH pb AS ({_POST_BRANDS})
        SELECT {_PLATFORM_EXPR} AS platform, b.display_name AS vendor,
               b.id AS brand_id, COUNT(DISTINCT a.uri) AS mentions
        FROM pb
        JOIN articles a ON a.uri = pb.article_uri
        JOIN bw_brands b ON b.id = pb.brand_id
        JOIN bw_market_brands mb ON mb.brand_id = b.id AND mb.market_id = :m
        WHERE COALESCE(a.bias_source, '') <> 'vendor:linkedin'
          AND a.social_meta IS NOT NULL
          {window}
        GROUP BY 1, 2, 3
    """), params).mappings().all()

    shared_rows = conn.execute(text(f"""
        WITH pb AS ({_POST_BRANDS})
        SELECT {_PLATFORM_EXPR} AS platform, b.display_name AS vendor,
               b.id AS brand_id,
               SUM(COALESCE((a.social_meta->>'reposts')::numeric,
                            (a.social_meta->>'shares')::numeric, 0)) AS shares
        FROM pb
        JOIN articles a ON a.uri = pb.article_uri
        JOIN bw_brands b ON b.id = pb.brand_id
        JOIN bw_market_brands mb ON mb.brand_id = b.id AND mb.market_id = :m
        WHERE a.social_meta IS NOT NULL
          {window}
        GROUP BY 1, 2, 3
        HAVING SUM(COALESCE((a.social_meta->>'reposts')::numeric,
                            (a.social_meta->>'shares')::numeric, 0)) > 0
    """), params).mappings().all()

    post_rows = conn.execute(text(f"""
        SELECT {_PLATFORM_EXPR} AS platform, a.uri, a.title,
               COALESCE(a.social_meta->>'author_name', a.social_meta->>'author')
                   AS author,
               a.news_source,
               COALESCE(a.bias_source, '') = 'vendor:linkedin' AS is_owned,
               -- On the vendor's channel but not the vendor's words. Kept
               -- beside is_owned rather than folded into it, so a reshare is
               -- labelled as one instead of silently becoming third-party
               -- coverage.
               (COALESCE(a.bias_source, '') = 'vendor:linkedin'
                AND NOT {_OWN_VOICE}) AS is_reshare,
               COALESCE((a.social_meta->>'likes')::numeric, 0)
                 + COALESCE((a.social_meta->>'comments')::numeric, 0)
                 + COALESCE((a.social_meta->>'reposts')::numeric,
                            (a.social_meta->>'shares')::numeric, 0)
                 AS engagement
        FROM bw_market_articles ma
        JOIN articles a ON a.uri = ma.article_uri
        WHERE ma.market_id = :m AND a.social_meta IS NOT NULL {window}
        ORDER BY engagement DESC
        LIMIT 500
    """), params).mappings().all()

    by_platform: Dict[str, Dict[str, Any]] = {}

    def _bucket(platform: Optional[str]) -> Optional[Dict[str, Any]]:
        # An empty-string platform is a real gap in this schema — social_meta
        # can hold "" rather than NULL — not a fourth network worth a card.
        if not platform:
            return None
        return by_platform.setdefault(platform, {
            "platform": platform, "most_discussed": [], "most_shared": [],
            "top_posts": [], "total_mentions": 0,
        })

    discussed_by_platform: Dict[str, List[Dict[str, Any]]] = {}
    for r in discussed_rows:
        b = _bucket(r["platform"])
        if b is None:
            continue
        discussed_by_platform.setdefault(r["platform"], []).append(dict(r))
        b["total_mentions"] += r["mentions"]

    shared_by_platform: Dict[str, List[Dict[str, Any]]] = {}
    for r in shared_rows:
        b = _bucket(r["platform"])
        if b is None:
            continue
        shared_by_platform.setdefault(r["platform"], []).append(
            {**dict(r), "shares": float(r["shares"])})

    posts_by_platform: Dict[str, List[Dict[str, Any]]] = {}
    for r in post_rows:
        b = _bucket(r["platform"])
        if b is None or r["engagement"] <= 0:
            continue
        posts_by_platform.setdefault(r["platform"], []).append(
            {**dict(r), "engagement": float(r["engagement"])})

    for platform, bucket in by_platform.items():
        bucket["most_discussed"] = sorted(
            discussed_by_platform.get(platform, []),
            key=lambda x: -x["mentions"])[:LEADERBOARD_LIMIT]
        bucket["most_shared"] = sorted(
            shared_by_platform.get(platform, []),
            key=lambda x: -x["shares"])[:LEADERBOARD_LIMIT]
        bucket["top_posts"] = sorted(
            posts_by_platform.get(platform, []),
            key=lambda x: -x["engagement"])[:LEADERBOARD_LIMIT]

    networks = sorted(by_platform.values(), key=lambda b: -b["total_mentions"])
    for b in networks:
        del b["total_mentions"]

    return {"networks": networks, "days": days}


def career_moves(conn, market_id: int, *, days: Optional[int] = None,
                 limit: int = 25) -> Dict[str, Any]:
    """Named hires and senior appointments, drawn from the review pass.

    Not a new signal — ``review_kind = 'hiring'`` already means the reviewer
    read a "welcome to the team" style post and named who joined in
    ``review_reason`` ("Ryan Burke as VP Sales"). This just surfaces those
    rows as their own list instead of leaving them folded into the general
    announcement count, where "who joined" was invisible next to "who has an
    open role" (a completely different signal, sourced from job listings,
    not from posts).
    """
    window = ""
    params: Dict[str, Any] = {"m": market_id, "lim": limit}
    if days:
        window = "AND COALESCE(a.publication_date, a.submission_date) >= :since"
        params["since"] = _iso_days_ago(days)

    rows = [dict(r) for r in conn.execute(text(f"""
        WITH pb AS ({_POST_BRANDS})
        SELECT DISTINCT ON (a.uri)
               b.display_name AS vendor, b.id AS brand_id, a.title, a.uri,
               ma.review_reason,
               COALESCE(a.publication_date, a.submission_date) AS published
        FROM pb
        JOIN articles a ON a.uri = pb.article_uri
        JOIN bw_brands b ON b.id = pb.brand_id
        JOIN bw_market_brands mb ON mb.brand_id = b.id AND mb.market_id = :m
        JOIN bw_market_articles ma ON ma.article_uri = a.uri AND ma.market_id = :m
        WHERE ma.review_kind = 'hiring' AND ma.review_verdict = 'signal'
          {window}
        ORDER BY a.uri, published DESC
    """), params).mappings().all()]
    rows.sort(key=lambda r: r.get("published") or "", reverse=True)

    in_scope = conn.execute(text("""
        SELECT COUNT(*) FROM bw_market_brands
        WHERE market_id = :m AND role <> 'excluded'
    """), {"m": market_id}).scalar() or 0
    vendors_with_moves = len({r["brand_id"] for r in rows})

    return {
        "moves": rows[:limit],
        "days": days,
        "coverage": _coverage(vendors_with_moves, in_scope,
                              "vendors have a named hire this period"),
    }


def period_comparison(conn, market_id: int, *, days: int = 30) -> Dict[str, Any]:
    """This reporting period against the immediately preceding one, same length.

    Deliberately narrow: only counts that are cheap and exact to bound by
    date — announcement-kind counts, job postings observed, and matched
    coverage volume. Headcount and Crunchbase already have their own as-of
    windowed trend charts elsewhere (``market_publish.headcount_trend``,
    ``funding_momentum``); re-deriving a delta for them here on a different
    date-bounding approach would risk quietly disagreeing with those charts.
    """
    from datetime import datetime, timedelta, timezone

    now = datetime.now(timezone.utc)
    curr_start_dt = now - timedelta(days=days)
    prev_start_dt = now - timedelta(days=days * 2)
    curr_start, curr_end = _iso_days_ago(days), _iso_days_ago(0)
    prev_start, prev_end = _iso_days_ago(days * 2), curr_start

    def _kinds(start: str, end: str) -> Dict[str, int]:
        rows = conn.execute(text("""
            SELECT COALESCE(ma.review_kind, 'other') AS kind,
                   COUNT(DISTINCT a.uri) AS n
            FROM bw_market_articles ma
            JOIN articles a ON a.uri = ma.article_uri
            WHERE ma.market_id = :m AND ma.review_verdict = 'signal'
              AND COALESCE(a.publication_date, a.submission_date) >= :start
              AND COALESCE(a.publication_date, a.submission_date) < :end
            GROUP BY 1
        """), {"m": market_id, "start": start, "end": end}).fetchall()
        return {kind: n for kind, n in rows}

    def _jobs(start_dt, end_dt) -> int:
        return conn.execute(text("""
            SELECT COUNT(DISTINCT s.provider_item_id)
            FROM bw_vendor_snapshots s
            JOIN bw_market_brands mb ON mb.brand_id = s.brand_id
                                     AND mb.market_id = :m
            WHERE s.snapshot_type = 'job_posting'
              AND s.observed_at >= :start AND s.observed_at < :end
        """), {"m": market_id, "start": start_dt, "end": end_dt}).scalar() or 0

    def _coverage_volume(start: str, end: str) -> int:
        return conn.execute(text("""
            SELECT COUNT(*) FROM bw_market_articles ma
            JOIN articles a ON a.uri = ma.article_uri
            WHERE ma.market_id = :m
              AND COALESCE(a.publication_date, a.submission_date) >= :start
              AND COALESCE(a.publication_date, a.submission_date) < :end
        """), {"m": market_id, "start": start, "end": end}).scalar() or 0

    current = _kinds(curr_start, curr_end)
    previous = _kinds(prev_start, prev_end)
    current["_jobs"] = _jobs(curr_start_dt, now)
    previous["_jobs"] = _jobs(prev_start_dt, curr_start_dt)
    current["_coverage"] = _coverage_volume(curr_start, curr_end)
    previous["_coverage"] = _coverage_volume(prev_start, prev_end)

    all_keys = set(current) | set(previous)
    deltas = {k: current.get(k, 0) - previous.get(k, 0) for k in all_keys}

    return {
        "days": days,
        "current_range": (curr_start[:10], curr_end[:10]),
        "previous_range": (prev_start[:10], prev_end[:10]),
        "current": current,
        "previous": previous,
        "deltas": deltas,
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
