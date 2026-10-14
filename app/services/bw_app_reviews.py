"""Google Play and App Store reviews for Brand Watcher.

Spec: docs/APP_STORE_REVIEWS_SPEC.md.

A brand lists its apps in ``bw_brands.config['app_store_targets']``, one entry
per app per country store::

    {"store": "google_play", "app_id": "com.rementr", "country": "GB", "language": "en"}
    {"store": "app_store",   "app_id": "1556652646",  "country": "de"}

and turns the sources on with ``extra_sources: ["google_play", "app_store"]``.
``bw_official_sources.poll_official_sources`` calls :func:`fetch_app_reviews`
once a day per brand and lands the rows it returns like any other official
record. This module owns everything store-specific: the scraper calls, the
mapping of a review to an article row, the daily rating snapshot, the call log
and the monthly record cap.

We never store the reviewer's name. Health app reviews often describe the
writer's own conditions ("I'm severely disabled and have multiple health
conditions"), and a name next to that text is a list of named people with
their health details, which we have no reason to hold.

The scheduled path calls Bright Data's REST dataset API through the client the
Market Monitor already uses, with the site's ``BRIGHTDATA_API_KEY``. We found
and tested these datasets through Bright Data's MCP server on 13 Oct 2026
(snapshot sd_mv72982jnx6gz1cnh); MCP is for agents, not scheduled jobs.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import text

logger = logging.getLogger(__name__)

STORES = ("google_play", "app_store")

#: Bright Data's review scrapers, confirmed with get_scraper_details on
#: 13-14 Oct 2026.
GOOGLE_PLAY_DATASET = "gd_m6zagkt024uwvvwuyu"
APP_STORE_DATASET = "gd_m734msue16e0adkbit"

#: Google Play reviews asked for per target per call. The scraper does not
#: return newest first, so start_date does the windowing and this only caps
#: what one call can cost.
MAX_REVIEWS_PER_CALL = 50

#: Google Play's num_of_reviews caps a call; the App Store scraper takes only a
#: URL, so the most one call can return is unknown. This is the figure the cap
#: check assumes before an App Store call, until we have measured one.
APP_STORE_ASSUMED_RECORDS = 100

#: Records a site may fetch per calendar month across all its brands. At
#: $2.50 per 1,000 records, 4,000 is about $10.
DEFAULT_MONTHLY_RECORDS = 4000

#: Who writes a store review. A brand whose app is a health service sets
#: config.app_review_author_role = "patient".
DEFAULT_AUTHOR_ROLE = "customer"

SOURCE_LABEL = {"google_play": "Google Play", "app_store": "App Store"}


def _dataset(store: str) -> str:
    if store == "google_play":
        return os.getenv("BRIGHTDATA_GOOGLE_PLAY_REVIEWS_DATASET_ID", GOOGLE_PLAY_DATASET)
    return os.getenv("BRIGHTDATA_APP_STORE_REVIEWS_DATASET_ID", APP_STORE_DATASET)


def monthly_record_cap() -> int:
    try:
        return int(os.getenv("BW_APP_REVIEWS_MONTHLY_RECORDS", "") or DEFAULT_MONTHLY_RECORDS)
    except ValueError:
        return DEFAULT_MONTHLY_RECORDS


# ---------------------------------------------------------------------------
# Targets and URLs
# ---------------------------------------------------------------------------

def targets_for(cfg: Dict[str, Any], store: str) -> List[Dict[str, str]]:
    """The brand's valid targets for one store. Bad entries are logged and skipped."""
    out = []
    for t in (cfg or {}).get("app_store_targets") or []:
        if not isinstance(t, dict) or t.get("store") != store:
            continue
        app_id = str(t.get("app_id") or "").strip()
        country = str(t.get("country") or "").strip()
        if not app_id or not country:
            logger.warning("app reviews: target without app_id or country skipped: %r", t)
            continue
        if store == "app_store":
            app_id = app_id.lower().removeprefix("id")
            if not app_id.isdigit():
                logger.warning("app reviews: App Store id %r is not numeric, skipped", t.get("app_id"))
                continue
        out.append({"store": store, "app_id": app_id, "country": country,
                    "language": str(t.get("language") or "").strip()})
    return out


def store_url(target: Dict[str, str]) -> str:
    if target["store"] == "google_play":
        return f"https://play.google.com/store/apps/details?id={target['app_id']}"
    return f"https://apps.apple.com/{target['country'].lower()}/app/id{target['app_id']}"


def review_uri(target: Dict[str, str], review_id: str) -> str:
    """A stable, unique article URI for one review.

    Neither scraper returns a link to the review itself. Google Play opens a
    review from ``reviewId``; the App Store has no per-review page, so the
    fragment only keeps the URI unique.
    """
    if target["store"] == "google_play":
        return f"{store_url(target)}&reviewId={review_id}"
    return f"{store_url(target)}#review-{review_id}"


# ---------------------------------------------------------------------------
# Mapping
# ---------------------------------------------------------------------------

def _review_day(value: Any) -> Optional[str]:
    """YYYY-MM-DD from the scraper's review_date, or None."""
    s = str(value or "").strip()
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00")).date().isoformat()
    except ValueError:
        return s[:10] if len(s) >= 10 and s[4] == "-" else None


def _rating(value: Any) -> Optional[int]:
    try:
        r = int(round(float(value)))
    except (TypeError, ValueError):
        return None
    return r if 1 <= r <= 5 else None


def _sentiment(rating: Optional[int]) -> Optional[str]:
    if rating is None:
        return None
    return "Positive" if rating >= 4 else "Negative" if rating <= 2 else "Neutral"


def _head(textv: str, n: int = 80) -> str:
    one_line = " ".join((textv or "").split())
    return one_line if len(one_line) <= n else one_line[: n - 1].rstrip() + "…"


def map_review(rec: Dict[str, Any], target: Dict[str, str],
               brand_name: str) -> Optional[Dict[str, Any]]:
    """One scraper record → the row ``_land_and_attribute`` expects, plus
    ``social_meta``. Returns None for records we cannot use (errors, no id)."""
    if rec.get("error") or rec.get("error_code"):
        return None
    rid = str(rec.get("review_id") or "").strip()
    if not rid:
        return None
    body = str(rec.get("review") or "").strip()
    title_text = str(rec.get("review_title") or "").strip()  # App Store only
    rating = _rating(rec.get("review_rating"))
    label = SOURCE_LABEL[target["store"]]
    stars = f" ({rating}/5)" if rating is not None else ""
    headline = title_text or _head(body) or "Review"
    summary = body
    if title_text and body:
        summary = f"{title_text}. {body}"
    reply = str(rec.get("developer_response") or "").strip()
    if reply:
        summary = f"{summary}\n\n{brand_name} replied: {reply}"
    meta = {
        "store": target["store"],
        "app_id": target["app_id"],
        "country": target["country"],
        "rating": rating,
        "found_helpful": rec.get("found_helpful"),
        "app_version": rec.get("app_latest_version"),
        "has_developer_reply": bool(reply),
    }
    return {
        "title": f"{label} review{stars}: {headline}"[:300],
        "summary": summary[:4000] or None,
        "url": review_uri(target, rid),
        "author": None,
        "published_at": _review_day(rec.get("review_date")),
        "sentiment": _sentiment(rating),
        "social_meta": {k: v for k, v in meta.items() if v is not None},
    }


def app_figures(records: List[Dict[str, Any]], target: Dict[str, str]) -> Optional[Dict[str, Any]]:
    """The app's own figures from a batch, for the daily snapshot.

    Google Play repeats ``app_rating``, ``app_number_of_reviews`` and
    ``app_downloads`` on every record. The App Store scraper returns no
    app-level rating, so its snapshot holds only what we can count:
    reviews fetched and the share that carry a developer reply.
    """
    good = [r for r in records if not (r.get("error") or r.get("error_code"))]
    if not good:
        return None
    if target["store"] == "google_play":
        first = good[0]

        def _num(v, cast):
            try:
                return cast(v) if v is not None else None
            except (TypeError, ValueError):
                return None
        rating = _num(first.get("app_rating"), float)
        return {
            "rating": round(rating, 2) if rating is not None else None,
            "review_count": _num(first.get("app_number_of_reviews"), int),
            "downloads": _num(first.get("app_downloads"), int),
            "data": {"app_title": first.get("app_title"),
                     "app_country": first.get("app_country"),
                     "app_content_rating": first.get("app_content_rating"),
                     "fetched": len(good)},
        }
    replied = sum(1 for r in good if str(r.get("developer_response") or "").strip())
    return {
        "rating": None, "review_count": None, "downloads": None,
        "data": {"fetched": len(good), "with_reply": replied,
                 "reply_share": round(replied / len(good), 3),
                 "app_latest_version": good[0].get("app_latest_version")},
    }


# ---------------------------------------------------------------------------
# Call log, cap and snapshots
# ---------------------------------------------------------------------------

def records_this_month(conn) -> int:
    return int(conn.execute(text("""
        SELECT COALESCE(SUM(records), 0) FROM bw_app_review_calls
        WHERE called_at >= date_trunc('month', NOW())
    """)).scalar() or 0)


def _log_call(conn, brand_id: int, target: Dict[str, str], records: int,
              ok: bool, error: Optional[str] = None) -> None:
    conn.execute(text("""
        INSERT INTO bw_app_review_calls
            (brand_id, store, app_id, country, records, ok, error)
        VALUES (:b, :s, :a, :c, :n, :ok, :e)
    """), {"b": brand_id, "s": target["store"], "a": target["app_id"],
           "c": target["country"], "n": records, "ok": ok,
           "e": (error or "")[:500] or None})


def save_snapshot(conn, brand_id: int, target: Dict[str, str],
                  figures: Dict[str, Any], day: Optional[str] = None) -> None:
    conn.execute(text("""
        INSERT INTO bw_app_snapshots
            (brand_id, store, app_id, country, snapshot_date,
             rating, review_count, downloads, data)
        VALUES (:b, :s, :a, :c, CAST(:d AS date), :r, :rc, :dl, CAST(:data AS jsonb))
        ON CONFLICT (brand_id, store, app_id, country, snapshot_date) DO UPDATE
            SET rating = EXCLUDED.rating, review_count = EXCLUDED.review_count,
                downloads = EXCLUDED.downloads, data = EXCLUDED.data
    """), {"b": brand_id, "s": target["store"], "a": target["app_id"],
           "c": target["country"],
           "d": day or datetime.now(timezone.utc).date().isoformat(),
           "r": figures.get("rating"), "rc": figures.get("review_count"),
           "dl": figures.get("downloads"),
           "data": json.dumps(figures.get("data") or {})})


# ---------------------------------------------------------------------------
# Fetch
# ---------------------------------------------------------------------------

def _payload(target: Dict[str, str], since: datetime) -> Dict[str, Any]:
    if target["store"] == "app_store":
        return {"url": store_url(target)}
    p: Dict[str, Any] = {"url": store_url(target), "num_of_reviews": MAX_REVIEWS_PER_CALL,
                         "country": target["country"].upper(),
                         # The scraper's date type is not documented further than
                         # "date"; reviews older than ``since`` are dropped below
                         # whatever it does with this.
                         "start_date": since.date().isoformat()}
    if target["language"]:
        p["language"] = target["language"]
    return p


async def _scrape(store: str, payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    from app.services.brightdata_linkedin import LinkedInDatasetClient, api_key
    client = LinkedInDatasetClient(api_key())
    return await client.scrape_sync(_dataset(store), [payload])


async def fetch_app_reviews(conn, brand: Dict[str, Any], cfg: Dict[str, Any],
                            store: str, since: datetime,
                            scrape=None) -> Tuple[List[Dict[str, Any]], bool]:
    """Fetch every target of one store for one brand.

    Returns ``(rows, complete)``. ``complete`` is False when any target failed
    or was skipped for the monthly cap, so the caller keeps the cursor where it
    was and the missed day is fetched again tomorrow. Each call is logged in
    ``bw_app_review_calls`` and committed with the caller's transaction.
    """
    scrape = scrape or _scrape
    since_day = since.date().isoformat()
    cap = monthly_record_cap()
    rows: List[Dict[str, Any]] = []
    complete = True
    for target in targets_for(cfg, store):
        expected = MAX_REVIEWS_PER_CALL if store == "google_play" else APP_STORE_ASSUMED_RECORDS
        used = records_this_month(conn)
        if used + expected > cap:
            logger.warning("app reviews: monthly cap reached (%d of %d records) — %s %s %s skipped",
                           used, cap, store, target["app_id"], target["country"])
            complete = False
            continue
        try:
            records = await scrape(store, _payload(target, since))
        except Exception as e:                                   # noqa: BLE001
            logger.error("app reviews: %s %s %s failed: %s",
                         store, target["app_id"], target["country"], e)
            _log_call(conn, brand["id"], target, 0, False, str(e))
            complete = False
            continue
        _log_call(conn, brand["id"], target, len(records), True)
        figures = app_figures(records, target)
        if figures:
            save_snapshot(conn, brand["id"], target, figures)
        for rec in records:
            row = map_review(rec, target, brand["display_name"])
            if row is None:
                continue
            if row["published_at"] and row["published_at"] < since_day:
                continue  # older than the window: the App Store has no date input
            rows.append(row)
    return rows, complete


def author_role_for(cfg: Dict[str, Any]) -> str:
    role = str((cfg or {}).get("app_review_author_role") or "").strip()
    return role or DEFAULT_AUTHOR_ROLE


def finish_landed(conn, landed: List[str], rows: List[Dict[str, Any]],
                  cfg: Dict[str, Any]) -> None:
    """Store social_meta and author role on newly landed reviews, and
    translate the ones that are not in English."""
    if not landed:
        return
    by_uri = {r["url"]: r for r in rows}
    role = author_role_for(cfg)
    for uri in landed:
        r = by_uri.get(uri)
        if r is None:
            continue
        conn.execute(text("""
            UPDATE articles SET social_meta = CAST(:m AS jsonb), author_role = :role,
                   author_role_reason = 'app store review'
            WHERE uri = :uri
        """), {"uri": uri, "m": json.dumps(r.get("social_meta") or {}), "role": role})
        try:
            from app.services.market_collect import _translate_landed
            _translate_landed(conn, uri, r.get("title") or "", r.get("summary") or "")
        except Exception as e:                                   # noqa: BLE001
            logger.warning("app reviews: translation skipped for %s: %s", uri, e)


# ---------------------------------------------------------------------------
# Alert checks (called from brand_watcher_monitor.evaluate_adverse_alerts)
# ---------------------------------------------------------------------------

def rating_drops(conn, brand_id: int, rating_drop: float, lookback_days: int,
                 min_span_days: int) -> List[Dict[str, Any]]:
    """Apps whose rating fell by at least ``rating_drop``: the oldest snapshot
    inside the lookback against the latest, at least ``min_span_days`` apart."""
    rows = conn.execute(text("""
        WITH w AS (
            SELECT store, app_id, country, snapshot_date, rating,
                   ROW_NUMBER() OVER (PARTITION BY store, app_id, country
                                      ORDER BY snapshot_date ASC) AS first_n,
                   ROW_NUMBER() OVER (PARTITION BY store, app_id, country
                                      ORDER BY snapshot_date DESC) AS last_n
            FROM bw_app_snapshots
            WHERE brand_id = :b AND rating IS NOT NULL
              AND snapshot_date >= CURRENT_DATE - CAST(:lb AS integer)
        )
        SELECT o.store, o.app_id, o.country, o.snapshot_date, o.rating,
               n.snapshot_date, n.rating
        FROM w o JOIN w n USING (store, app_id, country)
        WHERE o.first_n = 1 AND n.last_n = 1
    """), {"b": brand_id, "lb": int(lookback_days)}).fetchall()
    out = []
    for store, app_id, country, d_old, r_old, d_new, r_new in rows:
        if (d_new - d_old).days < min_span_days:
            continue
        if float(r_old) - float(r_new) + 1e-9 < rating_drop:
            continue
        out.append({"store": store, "app_id": app_id, "country": country,
                    "from": d_old, "to": d_new,
                    "rating_old": float(r_old), "rating_new": float(r_new)})
    return out


def negative_counts(conn, brand_id: int, baseline_weeks: int) -> Tuple[int, float]:
    """(1-2 star reviews in the last 7 days, weekly mean over the
    ``baseline_weeks`` weeks before that)."""
    row = conn.execute(text("""
        SELECT
          COUNT(DISTINCT a.uri) FILTER (WHERE a.publication_date >= to_char(CURRENT_DATE - 7, 'YYYY-MM-DD')),
          COUNT(DISTINCT a.uri) FILTER (WHERE a.publication_date <  to_char(CURRENT_DATE - 7, 'YYYY-MM-DD'))
        FROM articles a
        JOIN bw_article_categories c ON c.article_uri = a.uri AND c.brand_id = :b
        WHERE a.news_source IN ('Google Play', 'App Store')
          AND (a.social_meta->>'rating') IN ('1', '2')
          AND a.publication_date >= to_char(CURRENT_DATE - 7 * (CAST(:w AS integer) + 1), 'YYYY-MM-DD')
    """), {"b": brand_id, "w": int(baseline_weeks)}).fetchone()
    recent, prior = int(row[0] or 0), int(row[1] or 0)
    return recent, (prior / baseline_weeks if baseline_weeks else 0.0)
