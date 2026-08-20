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
from typing import Any, Dict, List, Optional, Sequence
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


# All four kinds are in the feed. Vendor LinkedIn posts used to be excluded
# wholesale — 562 of them against 122 news articles buries everything — but
# every post is now read once and judged, and ``articles()`` only returns the
# ones judged to state a fact. 107 of the 562 do, including 42 launches, 16
# partnerships, 11 named customers, 2 raises and an acquisition, which are
# exactly the events a market monitor exists to catch.
DEFAULT_FEED_CLASSES = ("news", "vendor", "research", "social")


def _parse_stamp(value) -> Optional[datetime]:
    """A publication date out of a TEXT column, or None.

    ``articles.publication_date`` is TEXT in this schema and holds several
    shapes. A feed item with a wrong date sorts wrongly forever, so anything
    unparseable returns None and the caller falls back rather than guessing.
    """
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    text_value = (str(value) if value is not None else "").strip()
    if not text_value:
        return None
    cleaned = text_value.replace("Z", "+00:00")
    for candidate in (cleaned, cleaned[:19], cleaned[:10]):
        try:
            stamp = datetime.fromisoformat(candidate)
            return stamp if stamp.tzinfo else stamp.replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


def build_feed(conn, market: Dict[str, Any], *, base_url: str,
               limit: int = 50, kind: str = "all",
               classes: Optional[Sequence[str]] = None,
               days: Optional[int] = None) -> bytes:
    """The market as a subscribable feed: its articles and its events.

    An aggregator, not a change log. Items are the articles that matched the
    market's phrases — linked to the original publication, not to us — merged
    with the timeline's events and sorted by date.

    Each article item carries its kind as the first ``<category>``: news,
    vendor, social or research. A reader who cannot tell a vendor's own blog
    post from a trade-press story is being misled by the feed, and the
    distinction costs one element.

    Hand-rolled like the rest of this codebase's feed output — no third-party
    dependency for eighty lines of XML.
    """
    from app.services import market_corpus as mcorp

    topic = (market.get("config") or {}).get("collection", {}).get("topic_name")
    if not topic:
        topic = f"Market Monitoring {market['name']}"

    site = base_url.rstrip("/")
    market_id = market["id"]
    wanted = tuple(classes) if classes else DEFAULT_FEED_CLASSES
    items: List[Dict[str, Any]] = []

    if kind in ("all", "articles"):
        has_corpus = conn.execute(
            text("SELECT to_regclass('bw_market_articles')")).scalar()
        if has_corpus:
            for row in mcorp.articles(conn, market_id, limit=limit * 3,
                                      days=days, classes=wanted):
                stamp = _parse_stamp(row.get("published"))
                items.append({
                    "stamp": stamp or datetime.now(timezone.utc),
                    "dated": stamp is not None,
                    "title": row.get("title") or row["uri"],
                    "link": row["uri"],
                    "guid": row["uri"],
                    "permalink": True,
                    "description": row.get("summary") or row.get("title") or "",
                    "source": row.get("news_source"),
                    # The review's kind ("launch", "partnership") is a better
                    # category than a phrase match for a post that was judged
                    # rather than matched.
                    "categories": ([row["article_class"]]
                                   + ([row["review_kind"]]
                                      if row.get("review_kind") else [])
                                   + list(row.get("matched_terms") or [])[:5]),
                })

    if kind in ("all", "events"):
        events = conn.execute(text("""
            SELECT id, title, description, event_type, significance, event_date,
                   article_count, created_at
            FROM timeline_events
            WHERE scope_type = 'topic' AND scope_id = :sid AND is_stale = false
            ORDER BY event_date DESC, id DESC LIMIT :lim
        """), {"sid": topic, "lim": limit}).mappings().all()
        for e in events:
            stamp = _parse_stamp(e["event_date"]) or _parse_stamp(e["created_at"])
            items.append({
                "stamp": stamp or datetime.now(timezone.utc),
                "dated": stamp is not None,
                "title": e["title"],
                # An event has no source URL of its own, so it links to the
                # market's own page rather than to somebody else's article.
                "link": f"{site}/explore#market-event-{e['id']}",
                "guid": f"market-event-{e['id']}",
                "permalink": False,
                "description": e["description"] or e["title"],
                "source": None,
                "categories": ["event", e["event_type"], e["significance"]],
            })

    items.sort(key=lambda i: i["stamp"], reverse=True)
    items = items[:limit]

    parts = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        ('<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom" '
         'xmlns:dc="http://purl.org/dc/elements/1.1/">'),
        "<channel>",
        f"<title>{_esc(market['name'])} — Market Monitor</title>",
        f"<link>{_esc(site)}/explore</link>",
        f"<description>{_esc(market.get('question') or market['name'])}</description>",
        "<language>en</language>",
        f'<atom:link href="{_esc(site)}/api/market-monitor/markets/'
        f'{market_id}/feed.xml" rel="self" type="application/rss+xml" />',
        f"<lastBuildDate>{format_datetime(datetime.now(timezone.utc))}</lastBuildDate>",
    ]
    for item in items:
        parts += [
            "<item>",
            f"<title>{_esc(item['title'])}</title>",
            f"<link>{_esc(item['link'])}</link>",
            f'<guid isPermaLink="{"true" if item["permalink"] else "false"}">'
            f"{_esc(item['guid'])}</guid>",
            f"<description>{_esc(item['description'])}</description>",
        ]
        for cat in item["categories"]:
            if cat:
                parts.append(f"<category>{_esc(str(cat))}</category>")
        # dc:creator, not <source>. RSS 2.0's <source> requires a url
        # attribute pointing at the originating feed, and we do not know the
        # publication's feed URL — only its name. Putting our own URL there
        # would claim we published it.
        if item["source"]:
            parts.append(f"<dc:creator>{_esc(item['source'])}</dc:creator>")
        # An item with no usable date gets none rather than today's, which
        # would make it look new every time the feed is rebuilt.
        if item["dated"]:
            parts.append(f"<pubDate>{format_datetime(item['stamp'])}</pubDate>")
        parts.append("</item>")
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
    # ``role <> 'excluded'`` to match every other figure in this block. Without
    # it the excluded vendor was counted here and nowhere else, so the tile read
    # "38 of 82 watched, 83 observed at least once" — more observed than exist.
    coverage["observed"] = conn.execute(text("""
        SELECT COUNT(DISTINCT s.brand_id) FROM bw_vendor_snapshots s
        JOIN bw_market_brands mb ON mb.brand_id = s.brand_id
                                 AND mb.market_id = :m
                                 AND mb.role <> 'excluded'
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
               -- The round lives under funding_crunchbase, written by
               -- ingest_crunchbase. The importer only ever writes status,
               -- total_musd and notes into funding_baseline, so reading
               -- last_round from there returned NULL for every vendor and the
               -- UI's round label never appeared.
               mb.baseline->'funding_crunchbase'->>'last_round' AS last_round
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


# ---------------------------------------------------------------------------
# Data inventory and exports
# ---------------------------------------------------------------------------
#
# "Where can I see all of the data" was a fair question with no answer. The
# monitor writes to eight tables and the UI showed two of them. Everything the
# market has stored is listed here with a row count and a download, so nothing
# is collected into a place nobody can look at.

DATASETS = {
    "vendors": "One row per vendor: the registry plus its latest observations.",
    "articles": "News, vendor blogs and research matched to this market, with "
                "why each one matched. Vendor posts are in `posts`.",
    "posts": "Vendor LinkedIn posts with the review verdict on each.",
    "profiles": "LinkedIn company readings: headcount, followers, location.",
    "funding": "Crunchbase readings: rounds, investors, rank.",
    "jobs": "Open job listings seen at these vendors.",
    "pages": "Vendor web pages watched, and what changed on them.",
    "runs": "Every collection run: source, status, records, latency, error.",
    "tasks": "Data-quality questions raised during import or collection, open "
             "and resolved.",
}


def data_inventory(conn, market_id: int) -> List[Dict[str, Any]]:
    """What this market has stored, with row counts. Counts only."""
    counts = {
        "vendors": ("SELECT COUNT(*) FROM bw_market_brands WHERE market_id = :m",
                    "SELECT MAX(updated_at) FROM bw_market_brands WHERE market_id = :m"),
        # Counts must match what build_table() actually returns for the same
        # name, because the Data tab prints this count next to that download.
        # Social posts live in the `posts` dataset, so they are excluded here
        # or the two together claim 758 rows where 758 exist in total.
        "articles": ("""SELECT COUNT(*) FROM bw_market_articles ma
                        JOIN articles a ON a.uri = ma.article_uri
                        WHERE ma.market_id = :m
                          AND COALESCE(a.bias_source, '') <> 'vendor:linkedin'""",
                     "SELECT MAX(matched_at) FROM bw_market_articles WHERE market_id = :m"),
        "posts": ("""SELECT COUNT(*) FROM bw_market_articles
                     WHERE market_id = :m AND review_verdict IS NOT NULL""",
                  """SELECT MAX(reviewed_at) FROM bw_market_articles
                     WHERE market_id = :m"""),
        "profiles": (_snapshot_count("profile"), _snapshot_latest("profile")),
        "funding": (_snapshot_count("funding"), _snapshot_latest("funding")),
        "jobs": (_snapshot_count("job_posting"), _snapshot_latest("job_posting")),
        "pages": (_snapshot_count("page_state"), _snapshot_latest("page_state")),
        "runs": ("SELECT COUNT(*) FROM bw_collection_runs WHERE market_id = :m",
                 "SELECT MAX(started_at) FROM bw_collection_runs WHERE market_id = :m"),
        # All tasks, not only open ones: build_table exports the full history,
        # and a resolved question is part of the record of how the registry
        # was cleaned up.
        "tasks": ("SELECT COUNT(*) FROM bw_review_tasks WHERE market_id = :m",
                  "SELECT MAX(created_at) FROM bw_review_tasks WHERE market_id = :m"),
    }
    out = []
    for name, (count_sql, latest_sql) in counts.items():
        try:
            rows = conn.execute(text(count_sql), {"m": market_id}).scalar() or 0
            latest = conn.execute(text(latest_sql), {"m": market_id}).scalar()
        except Exception as exc:  # noqa: BLE001 — one missing table is not a broken page
            logger.warning("inventory count failed for %s: %s", name, exc)
            rows, latest = 0, None
        out.append({
            "dataset": name,
            "description": DATASETS[name],
            "rows": rows,
            "last_updated": latest.isoformat() if hasattr(latest, "isoformat") else latest,
        })
    return out


def _snapshot_count(kind: str) -> str:
    return f"""SELECT COUNT(*) FROM bw_vendor_snapshots s
               JOIN bw_market_brands mb ON mb.brand_id = s.brand_id
                                        AND mb.market_id = :m
               WHERE s.snapshot_type = '{kind}'"""


def _snapshot_latest(kind: str) -> str:
    return f"""SELECT MAX(s.observed_at) FROM bw_vendor_snapshots s
               JOIN bw_market_brands mb ON mb.brand_id = s.brand_id
                                        AND mb.market_id = :m
               WHERE s.snapshot_type = '{kind}'"""


def _snapshot_rows(conn, market_id: int, kind: str,
                   fields: List[str]) -> List[Dict[str, Any]]:
    """Flatten one snapshot type into rows, one JSON key per column.

    A field may be a nested path — ``diff.added_count`` reads
    ``data->'diff'->>'added_count'``. Without that, page-change counts have to
    be left out entirely, because the collector nests them under ``diff``.

    Field names here must match what the mapper actually stores. They did not:
    this asked for ``job_title`` where the mapper writes ``title``, and five of
    the six job columns came back empty in the UI and in the CSV.
    """
    def _sql(field: str) -> str:
        if "." in field:
            head, tail = field.split(".", 1)
            return f"s.data->'{head}'->>'{tail}' AS \"{field}\""
        return f"s.data->>'{field}' AS \"{field}\""

    selected = ", ".join(_sql(f) for f in fields)
    return [dict(r) for r in conn.execute(text(f"""
        SELECT b.display_name AS vendor, s.observed_at, {selected}
        FROM bw_vendor_snapshots s
        JOIN bw_market_brands mb ON mb.brand_id = s.brand_id
                                 AND mb.market_id = :m
        JOIN bw_brands b ON b.id = s.brand_id
        WHERE s.snapshot_type = :k
        ORDER BY b.display_name, s.observed_at DESC
    """), {"m": market_id, "k": kind}).mappings().all()]


def build_table(conn, market_id: int, dataset: str) -> List[Dict[str, Any]]:
    """One dataset as a list of flat rows, ready for CSV or a table."""
    if dataset == "vendors":
        return build_dataset(conn, market_id)

    if dataset in ("articles", "posts"):
        from app.services import market_corpus as mcorp

        rows = mcorp.articles(conn, market_id, limit=5000,
                              require_signal_for_social=False)
        if dataset == "posts":
            rows = [r for r in rows if r["article_class"] == "social"]
        else:
            rows = [r for r in rows if r["article_class"] != "social"]
        return [{
            "vendor_or_source": r.get("news_source"),
            "title": r.get("title"),
            "published": r.get("published"),
            "url": r.get("uri"),
            "kind": r.get("article_class"),
            "collected_for_topic": r.get("topic"),
            "phrase_score": r.get("score"),
            "matched_phrases": ", ".join(r.get("matched_terms") or []),
            "review_verdict": r.get("review_verdict"),
            "review_kind": r.get("review_kind"),
            "review_reason": r.get("review_reason"),
            "analysed": r.get("analyzed"),
            "sentiment": r.get("sentiment"),
        } for r in rows]

    # Every name below is checked against the mapper that writes it:
    # brightdata_linkedin.map_company_profile / map_crunchbase_company /
    # map_job_listing, and the page_state dict in tasks/market_monitor.py.
    if dataset == "profiles":
        return _snapshot_rows(conn, market_id, "profile", [
            "employee_count", "followers", "headquarters", "country",
            "industry", "founded", "website", "specialties"])
    if dataset == "funding":
        return _snapshot_rows(conn, market_id, "funding", [
            "num_funding_rounds", "last_funding_type", "num_investors",
            "investors", "lead_investors", "founders", "cb_rank",
            "growth_score", "growth_trend", "heat_score", "heat_trend",
            "employee_band", "operating_status", "ipo_status", "acquired_by"])
    if dataset == "jobs":
        return _snapshot_rows(conn, market_id, "job_posting", [
            "title", "location", "seniority", "function", "employment_type",
            "posted_date", "url"])
    if dataset == "pages":
        # `text` is deliberately absent — it is the full page body and would
        # make the CSV unusable.
        return _snapshot_rows(conn, market_id, "page_state", [
            "url", "kind", "title", "http_status",
            "diff.added_count", "diff.removed_count", "diff.moved_count",
            "diff.material"])

    if dataset == "runs":
        return [dict(r) for r in conn.execute(text("""
            SELECT source, provider, status, records_received, records_new,
                   records_skipped, started_at, completed_at, latency_ms, error
            FROM bw_collection_runs WHERE market_id = :m
            ORDER BY started_at DESC
        """), {"m": market_id}).mappings().all()]

    if dataset == "tasks":
        return [dict(r) for r in conn.execute(text("""
            SELECT t.kind, t.severity, t.status, t.field, t.message,
                   b.display_name AS vendor, t.created_at
            FROM bw_review_tasks t
            LEFT JOIN bw_brands b ON b.id = t.brand_id
            WHERE t.market_id = :m
            ORDER BY t.created_at DESC
        """), {"m": market_id}).mappings().all()]

    raise ValueError(f"unknown dataset: {dataset}")


def table_csv(rows: List[Dict[str, Any]]) -> str:
    """Rows to CSV. Columns come from the first row's keys."""
    if not rows:
        return ""
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=list(rows[0].keys()),
                            extrasaction="ignore")
    writer.writeheader()
    for row in rows:
        writer.writerow({k: ("" if v is None else v) for k, v in row.items()})
    return buf.getvalue()
