"""The market's outputs: a dataset, a feed, and a brief.

Collection fills a corpus; this is what a reader actually consumes.

- **Dataset** — the registry joined to its latest observations, one row per
  vendor. CSV for a spreadsheet, JSON for anything else. This is the thing you
  hand someone who asks "what is in this market".
- **Feed** — the market's timeline as RSS, so the wire can be subscribed to
  rather than visited.
- **Brief** — the weekly rollup and standing summary the timeline already
  generates, assembled into one document.

Nothing here collects or calls a provider. It reads what the monitor stored.
"""

import csv
import io
import json
import logging
from datetime import datetime, timezone
from email.utils import format_datetime
from typing import Any, Dict, List, Optional
from xml.sax.saxutils import escape

from sqlalchemy import text

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Dataset
# ---------------------------------------------------------------------------

DATASET_COLUMNS = [
    "vendor", "slug", "role", "collecting", "sub_category", "category",
    "country", "founded_year", "headcount_workbook", "headcount_linkedin",
    "followers_linkedin", "funding_status", "total_funding_musd",
    "funding_rounds", "last_round", "investors", "lead_investors",
    "growth_score", "heat_score", "cb_rank", "ipo_status",
    "website", "linkedin_url", "crunchbase_url",
    "posts_30d", "open_jobs", "articles_attributed", "last_observed",
]


def build_dataset(conn, market_id: int) -> List[Dict[str, Any]]:
    """One row per vendor: the registry plus its most recent observations.

    Workbook headcount and LinkedIn headcount are separate columns on purpose.
    They disagree — the workbook is a point in time and LinkedIn is today — and
    collapsing them would hide the very delta a market monitor exists to show.
    """
    rows = conn.execute(text("""
        SELECT
            b.id, b.display_name, b.name AS slug, mb.role, mb.collection_enabled,
            mb.baseline,
            (SELECT s.data FROM bw_vendor_snapshots s
             WHERE s.brand_id = b.id AND s.snapshot_type = 'profile'
             ORDER BY s.observed_at DESC LIMIT 1) AS profile,
            (SELECT s.data FROM bw_vendor_snapshots s
             WHERE s.brand_id = b.id AND s.snapshot_type = 'funding'
             ORDER BY s.observed_at DESC LIMIT 1) AS funding,
            (SELECT COUNT(*) FROM bw_vendor_snapshots s
             WHERE s.brand_id = b.id AND s.snapshot_type = 'job_posting') AS jobs,
            (SELECT COUNT(*) FROM bw_article_categories bac
             WHERE bac.brand_id = b.id) AS articles,
            (SELECT MAX(s.observed_at) FROM bw_vendor_snapshots s
             WHERE s.brand_id = b.id) AS last_observed
        FROM bw_market_brands mb
        JOIN bw_brands b ON b.id = mb.brand_id
        WHERE mb.market_id = :m
        ORDER BY mb.sort_order, b.display_name
    """), {"m": market_id}).mappings().all()

    posts = dict(conn.execute(text("""
        SELECT bac.brand_id, COUNT(DISTINCT a.uri)
        FROM bw_article_categories bac
        JOIN articles a ON a.uri = bac.article_uri
        WHERE a.bias_source = 'vendor:linkedin'
          AND COALESCE(a.publication_date, a.submission_date)
              >= (NOW() - INTERVAL '30 days')::text
        GROUP BY 1
    """)).fetchall())

    idents = {}
    for brand_id, kind, value in conn.execute(text("""
        SELECT i.brand_id, i.kind, i.display_value
        FROM bw_vendor_identifiers i
        JOIN bw_market_brands mb ON mb.brand_id = i.brand_id AND mb.market_id = :m
        WHERE i.valid_to IS NULL
          AND i.kind IN ('website_url', 'linkedin_company_url', 'crunchbase_url')
    """), {"m": market_id}).fetchall():
        idents.setdefault(brand_id, {})[kind] = value

    out: List[Dict[str, Any]] = []
    for r in rows:
        base = r["baseline"] if isinstance(r["baseline"], dict) else {}
        tax = base.get("taxonomy") or {}
        fund = base.get("funding_baseline") or {}
        metrics = base.get("metrics") or {}
        prof = r["profile"] if isinstance(r["profile"], dict) else {}
        cb = r["funding"] if isinstance(r["funding"], dict) else {}
        ids = idents.get(r["id"], {})
        out.append({
            "vendor": r["display_name"],
            "slug": r["slug"],
            "role": r["role"],
            "collecting": r["collection_enabled"],
            "sub_category": tax.get("sub_category"),
            "category": tax.get("category"),
            "country": base.get("hq_country"),
            "founded_year": base.get("founded_year"),
            "headcount_workbook": metrics.get("employee_count"),
            "headcount_linkedin": prof.get("employee_count"),
            "followers_linkedin": prof.get("followers"),
            "funding_status": fund.get("status"),
            # Empty for Undisclosed and Bootstrapped, and that is the data.
            "total_funding_musd": fund.get("total_musd"),
            "funding_rounds": cb.get("num_funding_rounds"),
            "last_round": cb.get("last_funding_type"),
            "investors": cb.get("num_investors"),
            "lead_investors": "; ".join(cb.get("lead_investors") or []),
            "growth_score": cb.get("growth_score"),
            "heat_score": cb.get("heat_score"),
            "cb_rank": cb.get("cb_rank"),
            "ipo_status": cb.get("ipo_status"),
            "website": ids.get("website_url"),
            "linkedin_url": ids.get("linkedin_company_url"),
            "crunchbase_url": ids.get("crunchbase_url"),
            "posts_30d": posts.get(r["id"], 0),
            "open_jobs": r["jobs"],
            "articles_attributed": r["articles"],
            "last_observed": r["last_observed"].isoformat() if r["last_observed"] else None,
        })
    return out


def dataset_csv(rows: List[Dict[str, Any]]) -> str:
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=DATASET_COLUMNS, extrasaction="ignore")
    writer.writeheader()
    for r in rows:
        writer.writerow(r)
    return buf.getvalue()


# ---------------------------------------------------------------------------
# Feed
# ---------------------------------------------------------------------------

def _esc(v: Any) -> str:
    return escape(str(v)) if v not in (None, "") else ""


def build_feed(conn, market: Dict[str, Any], *, base_url: str,
               limit: int = 50) -> bytes:
    """The market's timeline as RSS 2.0.

    Hand-rolled like the rest of this codebase's feed output — no third-party
    dependency for forty lines of XML. Each item is a timeline event, so a
    subscriber gets what changed rather than every article that mentioned the
    category.
    """
    topic = (market.get("config") or {}).get("collection", {}).get("topic_name")
    if not topic:
        topic = f"Market Monitoring {market['name']}"

    events = conn.execute(text("""
        SELECT id, title, description, event_type, significance, event_date,
               article_count, created_at
        FROM timeline_events
        WHERE scope_type = 'topic' AND scope_id = :sid AND is_stale = false
        ORDER BY event_date DESC, id DESC LIMIT :lim
    """), {"sid": topic, "lim": limit}).mappings().all()

    site = base_url.rstrip("/")
    parts = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom">',
        "<channel>",
        f"<title>{_esc(market['name'])} — Market Monitor</title>",
        f"<link>{_esc(site)}/explore</link>",
        f"<description>{_esc(market.get('question') or market['name'])}</description>",
        "<language>en</language>",
        f'<atom:link href="{_esc(site)}/api/market-monitor/markets/'
        f'{market["id"]}/feed.xml" rel="self" type="application/rss+xml" />',
        f"<lastBuildDate>{format_datetime(datetime.now(timezone.utc))}</lastBuildDate>",
    ]
    for e in events:
        stamp = e["created_at"] or datetime.now(timezone.utc)
        if stamp.tzinfo is None:
            stamp = stamp.replace(tzinfo=timezone.utc)
        guid = f"{site}/explore#market-event-{e['id']}"
        parts += [
            "<item>",
            f"<title>{_esc(e['title'])}</title>",
            f"<link>{_esc(guid)}</link>",
            f'<guid isPermaLink="false">market-event-{e["id"]}</guid>',
            f"<description>{_esc(e['description'] or e['title'])}</description>",
            f"<category>{_esc(e['event_type'])}</category>",
            f"<category>{_esc(e['significance'])}</category>",
            f"<pubDate>{format_datetime(stamp)}</pubDate>",
            "</item>",
        ]
    parts += ["</channel>", "</rss>"]
    return "\n".join(parts).encode("utf-8")


# ---------------------------------------------------------------------------
# Brief
# ---------------------------------------------------------------------------

def build_brief(conn, market: Dict[str, Any], *, days: int = 7) -> Dict[str, Any]:
    """The market brief: what changed, who moved, and what is still unknown.

    Assembled from stored rows, not generated fresh — the timeline already did
    the extraction, and re-asking a model to summarise what it summarised
    yesterday costs money to produce a different answer to the same question.
    """
    from app.services.timeline_rollup import get_state_doc

    topic = (market.get("config") or {}).get("collection", {}).get("topic_name")
    if not topic:
        topic = f"Market Monitoring {market['name']}"

    events = [dict(r) for r in conn.execute(text("""
        SELECT title, description, event_type, significance, event_date,
               article_count
        FROM timeline_events
        WHERE scope_type = 'topic' AND scope_id = :sid AND is_stale = false
          AND event_date >= CURRENT_DATE - (:d || ' days')::INTERVAL
        ORDER BY CASE significance WHEN 'critical' THEN 0 WHEN 'high' THEN 1
                                   WHEN 'medium' THEN 2 ELSE 3 END,
                 event_date DESC
    """), {"sid": topic, "d": str(days)}).mappings().all()]

    # Headcount movement: the newest profile against the workbook baseline.
    movers = [dict(r) for r in conn.execute(text("""
        SELECT b.display_name AS vendor,
               (mb.baseline->'metrics'->>'employee_count')::numeric AS was,
               (s.data->>'employee_count')::numeric AS now_count
        FROM bw_market_brands mb
        JOIN bw_brands b ON b.id = mb.brand_id
        JOIN LATERAL (
            SELECT data FROM bw_vendor_snapshots
            WHERE brand_id = mb.brand_id AND snapshot_type = 'profile'
            ORDER BY observed_at DESC LIMIT 1
        ) s ON TRUE
        WHERE mb.market_id = :m
          AND (mb.baseline->'metrics'->>'employee_count') IS NOT NULL
          AND (s.data->>'employee_count') IS NOT NULL
    """), {"m": market["id"]}).mappings().all()]
    for m in movers:
        m["delta"] = float(m["now_count"]) - float(m["was"])
        m["pct"] = round(m["delta"] / float(m["was"]) * 100, 1) if m["was"] else None
    movers.sort(key=lambda x: abs(x["delta"]), reverse=True)

    loudest = [dict(r) for r in conn.execute(text("""
        SELECT b.display_name AS vendor, COUNT(DISTINCT a.uri) AS posts
        FROM bw_article_categories bac
        JOIN bw_brands b ON b.id = bac.brand_id
        JOIN bw_market_brands mb ON mb.brand_id = b.id AND mb.market_id = :m
        JOIN articles a ON a.uri = bac.article_uri
        WHERE a.bias_source = 'vendor:linkedin'
          AND COALESCE(a.publication_date, a.submission_date)
              >= (NOW() - (:d || ' days')::INTERVAL)::text
        GROUP BY 1 ORDER BY 2 DESC LIMIT 10
    """), {"m": market["id"], "d": str(days)}).mappings().all()]

    coverage = conn.execute(text("""
        SELECT COUNT(*) FILTER (WHERE collection_enabled) AS watching,
               COUNT(*) AS registry,
               COUNT(*) FILTER (WHERE NOT collection_enabled) AS paused
        FROM bw_market_brands WHERE market_id = :m
    """), {"m": market["id"]}).mappings().first()

    gaps = [dict(r) for r in conn.execute(text("""
        SELECT severity, kind, COUNT(*) AS n FROM bw_review_tasks
        WHERE market_id = :m AND status = 'open'
        GROUP BY 1,2 ORDER BY 3 DESC
    """), {"m": market["id"]}).mappings().all()]

    try:
        state = get_state_doc(conn, "topic", topic)
    except Exception:  # noqa: BLE001 — a brief without the standing summary is still a brief
        state = None

    return {
        "market": market["name"],
        "question": market.get("question"),
        "period_days": days,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "standing_summary": (state or {}).get("summary"),
        "events": events,
        "headcount_movers": movers[:10],
        "loudest_vendors": loudest,
        "coverage": dict(coverage or {}),
        "open_questions": gaps,
    }


# ---------------------------------------------------------------------------
# Overview
# ---------------------------------------------------------------------------

def build_overview(conn, market: Dict[str, Any], *, days: int = 30
                   ) -> Dict[str, Any]:
    """One screen that answers "what is the state of this market".

    The brief answers "what changed in the last week". That is a different
    question, and asking a reader to infer the standing picture from a list of
    recent changes is why the tab had no overview worth reading. This is the
    standing picture: how much of the market is being watched, how much money
    is in it, who is active, what the coverage is about, and when we last
    looked.

    Every figure is a count of stored rows. Nothing here is generated, so no
    number in it can be a model's guess.
    """
    market_id = market["id"]
    since = f"(NOW() - INTERVAL '{int(days)} days')::text"

    coverage = dict(conn.execute(text("""
        SELECT COUNT(*) AS registry,
               COUNT(*) FILTER (WHERE role = 'excluded') AS excluded,
               COUNT(*) FILTER (WHERE collection_enabled AND role <> 'excluded')
                   AS watching,
               COUNT(*) FILTER (WHERE NOT collection_enabled AND role <> 'excluded')
                   AS paused
        FROM bw_market_brands WHERE market_id = :m
    """), {"m": market_id}).mappings().first() or {})

    # How much of the registry we have actually observed, as opposed to
    # switched on. The gap between "watching" and "observed" is the honest
    # measure of coverage.
    coverage["observed"] = conn.execute(text("""
        SELECT COUNT(DISTINCT s.brand_id) FROM bw_vendor_snapshots s
        JOIN bw_market_brands mb ON mb.brand_id = s.brand_id
                                 AND mb.market_id = :m
    """), {"m": market_id}).scalar() or 0

    funding = dict(conn.execute(text("""
        SELECT COUNT(*) FILTER (
                   WHERE baseline->'funding_baseline'->>'status' = 'Disclosed')
                   AS disclosed,
               COUNT(*) FILTER (
                   WHERE COALESCE(baseline->'funding_baseline'->>'status','')
                         <> 'Disclosed') AS undisclosed,
               SUM((baseline->'funding_baseline'->>'total_musd')::numeric)
                   AS total_musd
        FROM bw_market_brands
        WHERE market_id = :m AND role <> 'excluded'
    """), {"m": market_id}).mappings().first() or {})
    funding["total_musd"] = (float(funding["total_musd"])
                             if funding.get("total_musd") is not None else None)

    top_funded = [dict(r) for r in conn.execute(text("""
        SELECT b.display_name AS vendor, b.id AS brand_id,
               (mb.baseline->'funding_baseline'->>'total_musd')::numeric AS musd,
               mb.baseline->'funding_baseline'->>'last_round' AS last_round
        FROM bw_market_brands mb
        JOIN bw_brands b ON b.id = mb.brand_id
        WHERE mb.market_id = :m AND mb.role <> 'excluded'
          AND (mb.baseline->'funding_baseline'->>'total_musd') IS NOT NULL
        ORDER BY musd DESC NULLS LAST LIMIT 10
    """), {"m": market_id}).mappings().all()]
    for row in top_funded:
        row["musd"] = float(row["musd"]) if row["musd"] is not None else None

    activity = [dict(r) for r in conn.execute(text(f"""
        SELECT b.id AS brand_id, b.display_name AS vendor,
               (SELECT COUNT(DISTINCT a.uri)
                  FROM bw_article_categories bac
                  JOIN articles a ON a.uri = bac.article_uri
                 WHERE bac.brand_id = b.id
                   AND a.bias_source = 'vendor:linkedin'
                   AND COALESCE(a.publication_date, a.submission_date) >= {since}
               ) AS posts,
               (SELECT COUNT(*) FROM bw_vendor_snapshots s
                 WHERE s.brand_id = b.id AND s.snapshot_type = 'job_posting'
               ) AS jobs,
               (SELECT COUNT(*) FROM bw_article_categories bac2
                 WHERE bac2.brand_id = b.id) AS articles
        FROM bw_market_brands mb
        JOIN bw_brands b ON b.id = mb.brand_id
        WHERE mb.market_id = :m AND mb.role <> 'excluded'
    """), {"m": market_id}).mappings().all()]
    for row in activity:
        row["signals"] = (row["posts"] or 0) + (row["jobs"] or 0)
    activity.sort(key=lambda r: (r["signals"], r["articles"] or 0), reverse=True)
    quiet = [r for r in activity if r["signals"] == 0 and not r["articles"]]

    corpus: Dict[str, Any] = {}
    if conn.execute(text("SELECT to_regclass('bw_market_articles')")).scalar():
        from app.services import market_corpus as mcorp
        corpus = mcorp.summary(conn, market_id, days=days)

    last_runs = [dict(r) for r in conn.execute(text("""
        SELECT DISTINCT ON (source) source, status, records_received,
               started_at, completed_at, error
        FROM bw_collection_runs WHERE market_id = :m
        ORDER BY source, started_at DESC
    """), {"m": market_id}).mappings().all()]

    topic = (market.get("config") or {}).get("collection", {}).get("topic_name") \
        or f"Market Monitoring {market['name']}"
    latest_events = [dict(r) for r in conn.execute(text("""
        SELECT id, title, event_type, significance, event_date, article_count
        FROM timeline_events
        WHERE scope_type = 'topic' AND scope_id = :sid AND is_stale = false
        ORDER BY event_date DESC, id DESC LIMIT 8
    """), {"sid": topic}).mappings().all()]

    return {
        "market": market["name"],
        "market_id": market_id,
        "question": market.get("question"),
        "period_days": days,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "coverage": coverage,
        "funding": funding,
        "top_funded": top_funded,
        "most_active": activity[:10],
        "quiet_vendors": len(quiet),
        "corpus": corpus,
        "last_runs": last_runs,
        "latest_events": latest_events,
    }
