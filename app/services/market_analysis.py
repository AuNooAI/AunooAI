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

ANALYSES = ("formation", "signal_noise", "funding", "hiring")


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
    per_vendor: Dict[int, Dict[str, Any]] = {}
    for row in rows:
        group = _group_function(row["function"])
        by_function[group] = by_function.get(group, 0) + 1
        level = (row["seniority"] or "not stated").strip() or "not stated"
        by_seniority[level] = by_seniority.get(level, 0) + 1
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
        "by_vendor": sorted(per_vendor.values(),
                            key=lambda v: -v["openings"]),
        "coverage": _coverage(len(per_vendor), in_scope,
                              "vendors have job listings we have seen"),
    }


def run(conn, market_id: int, name: str) -> Dict[str, Any]:
    """Dispatch by name. Raises ValueError on an unknown analysis."""
    fn = {"formation": formation, "signal_noise": signal_noise,
          "funding": funding, "hiring": hiring}.get(name)
    if not fn:
        raise ValueError(f"unknown analysis: {name}")
    return fn(conn, market_id)
