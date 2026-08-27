"""One vendor against the market it was measured in (spec 4.16).

A benchmark is the easiest place on this page to publish a lie, because the
arithmetic works whatever you feed it. Three rules keep it honest.

**A vendor we did not measure is absent, not zero.** If a vendor's LinkedIn
collection failed, it has no post count. Putting it in the cohort at zero drags
every other vendor's percentile up and ranks the broken vendor last, and both
of those numbers are artefacts of an outage. Unmeasured vendors are returned
under ``unmeasured`` with the reason, and never enter the arithmetic.

**The comparator is independent of the vendor.** The selected vendor is removed
from the market and Top-20 aggregates, so "above the market median" cannot be
partly a statement about itself. Its percentile is the one exception, and is
computed against the full cohort including itself, because a rank has to be a
rank among everyone.

**Too small a cohort is refused, not shrunk.** Below five measured peers the
aggregates are withheld: a median of three is noise, and in a market of this
size it also names them. Between five and nineteen the comparator is labelled
"Top N available" rather than being passed off as a Top 20.

Each metric keeps its own clock. Observed jobs are as of the latest successful
run and headcount is the latest fresh reading; neither becomes a 30-day flow
because the page happens to default to 30 days.
"""

from __future__ import annotations

import logging
import statistics
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import text

from app.services import market_lists as mlists
from app.services import market_metrics as mmet
from app.services import market_publish as mpub
from app.services.market_corpus import earned_sql, own_voice_sql

logger = logging.getLogger(__name__)

#: Below this many measured peers there is no comparator. Five is the spec's
#: floor and it does two jobs: a median of four is not a market, and in an
#: 84-vendor registry a cohort of four is close to naming its members.
MIN_PEERS = 5

#: The headline cohort size. Fewer measured peers than this and the comparator
#: is relabelled rather than quietly renamed.
TOP_N = 20

_OWN_VOICE = own_voice_sql("a")


# ---------------------------------------------------------------------------
# What can be benchmarked
# ---------------------------------------------------------------------------

#: Every supported metric, with the clock it runs on and the collection it
#: depends on. ``window`` says whether the metric is a flow over the selected
#: period or a level as of the latest run — the distinction the spec insists
#: must survive into the UI, because "12 open roles" and "12 roles posted in
#: the last 30 days" are different claims.
METRICS: Dict[str, Dict[str, Any]] = {
    "headcount": {
        "label": "Observed LinkedIn headcount",
        "unit": "people",
        "window": "as_of",
        "source": "linkedin_company_profile",
        "as_of_note": "latest fresh reading",
    },
    "headcount_pct": {
        "label": "Headcount change",
        "unit": "percent",
        "window": "period",
        "source": "linkedin_company_profile",
        "as_of_note": "between the first and last readings inside the period",
    },
    "posts": {
        "label": "Owned LinkedIn posts",
        "unit": "posts",
        "window": "period",
        "source": "linkedin_company_post",
    },
    "mentions": {
        "label": "Earned mentions",
        "unit": "articles",
        "window": "period",
        "source": "corpus_match",
    },
    "announcements": {
        "label": "Announcement / factual-update posts",
        "unit": "posts",
        "window": "period",
        "source": "linkedin_company_post",
    },
    "jobs_open": {
        "label": "Observed active job listings",
        "unit": "listings",
        "window": "as_of",
        "source": "ats_jobs",
        "as_of_note": "as of the latest successful run",
    },
    "jobs_new": {
        "label": "Newly observed job listings",
        "unit": "listings",
        "window": "as_of",
        "source": "ats_jobs",
        "as_of_note": "between the two latest complete runs",
    },
    "funding": {
        "label": "Disclosed total funding",
        "unit": "musd",
        "window": "as_of",
        # No collector state to report. The disclosed total is the imported
        # baseline, not something a source polls, so reporting a collection
        # run beside it would attach the wrong provenance to the number.
        "source": None,
        "as_of_note": "current imported baseline",
    },
    "activity_index": {
        "label": "Activity Index",
        "unit": "index",
        "window": "period",
        "source": "linkedin_company_post",
        "as_of_note": "scored only where all three channels are healthy",
    },
}


def available_metrics() -> List[Dict[str, Any]]:
    """The metric picker, in the order the spec lists them."""
    return [{"key": k, **{f: v for f, v in m.items() if f != "source"}}
            for k, m in METRICS.items()]


# ---------------------------------------------------------------------------
# Per-metric values across the whole eligible cohort
# ---------------------------------------------------------------------------

def _eligible(conn, market_id: int) -> Dict[int, str]:
    """Vendor ids in this market that a benchmark may consider, with names."""
    return {int(r[0]): r[1] for r in conn.execute(text("""
        SELECT mb.brand_id, b.display_name
          FROM bw_market_brands mb
          JOIN bw_brands b ON b.id = mb.brand_id
         WHERE mb.market_id = :m AND mb.role <> 'excluded'
    """), {"m": market_id}).fetchall()}


def _headcount_values(conn, market_id: int, days: int, pct: bool
                      ) -> Tuple[Dict[int, float], Dict[int, str], Optional[str]]:
    """Latest fresh headcount, or its change across the period.

    Freshness is judged against the profile collector's own cadence, not a
    fixed threshold, because a weekly poll is not stale at three days.
    """
    state = mmet.collection_state(conn, market_id, "linkedin_company_profile")
    cadence = state["freshness"]["expected_interval_seconds"]

    rows = conn.execute(text(f"""
        WITH readings AS (
            SELECT s.brand_id, s.observed_at,
                   (s.data->>'employee_count')::numeric AS headcount
              FROM bw_vendor_snapshots s
              JOIN bw_market_brands mb ON mb.brand_id = s.brand_id
                   AND mb.market_id = :m AND mb.role <> 'excluded'
             WHERE s.snapshot_type = 'profile'
               AND {mpub.EXACT_HEADCOUNT}
               {"AND s.observed_at >= NOW() - (:d || ' days')::interval"
                if pct else ""}
        )
        SELECT brand_id,
               (ARRAY_AGG(headcount ORDER BY observed_at DESC))[1] AS latest,
               MAX(observed_at) AS latest_at,
               (ARRAY_AGG(headcount ORDER BY observed_at))[1] AS earliest,
               MIN(observed_at) AS earliest_at,
               COUNT(*) AS readings
          FROM readings GROUP BY brand_id
    """), {"m": market_id, "d": days}).mappings().all()

    from datetime import datetime, timezone
    now = datetime.now(timezone.utc)
    values: Dict[int, float] = {}
    unmeasured: Dict[int, str] = {}
    as_of: Optional[str] = None

    for r in rows:
        bid = int(r["brand_id"])
        latest_at = r["latest_at"]
        if latest_at and (as_of is None or latest_at.isoformat() > as_of):
            as_of = latest_at.isoformat()
        if not pct:
            fresh = bool(latest_at and
                         (now - latest_at).total_seconds() <= cadence * 2)
            if fresh:
                values[bid] = float(r["latest"])
            else:
                unmeasured[bid] = ("the last LinkedIn profile reading is older "
                                   "than two collection intervals")
            continue
        # A change needs two readings inside the window. One reading is not a
        # vendor that did not move; it is a vendor we read once.
        if int(r["readings"]) < 2 or not r["earliest"]:
            unmeasured[bid] = ("only one LinkedIn reading inside this period, "
                               "so there is nothing to compare it against")
            continue
        was = float(r["earliest"])
        values[bid] = round((float(r["latest"]) - was) / was * 100, 1)

    return values, unmeasured, as_of


def _post_values(conn, market_id: int, days: int, *, kind: str
                 ) -> Dict[int, float]:
    """Owned posts, earned mentions or reviewed announcements, per vendor.

    Counts ``DISTINCT (brand, uri)`` for the same reason the post list does: a
    post filed under three categories is three rows in
    ``bw_article_categories`` and would otherwise be counted three times.
    """
    if kind == "mentions":
        clause = earned_sql("a", "bac")
        source = ""
    else:
        clause = _OWN_VOICE
        source = "AND COALESCE(a.bias_source,'') = 'vendor:linkedin'"
    verdict = ("AND r.review_verdict = 'signal'" if kind == "announcements"
               else "")
    join = ("LEFT JOIN bw_market_articles r ON r.article_uri = a.uri "
            "AND r.market_id = mb.market_id") if verdict else ""

    return {int(b): float(n) for b, n in conn.execute(text(f"""
        SELECT brand_id, COUNT(*) FROM (
            SELECT DISTINCT bac.brand_id, a.uri
              FROM bw_article_categories bac
              JOIN articles a ON a.uri = bac.article_uri
              JOIN bw_market_brands mb ON mb.brand_id = bac.brand_id
                   AND mb.market_id = :m AND mb.role <> 'excluded'
              {join}
             WHERE {clause} {source} {verdict}
               AND COALESCE(a.publication_date, a.submission_date)
                   >= (NOW() - (:d || ' days')::interval)::text
        ) t GROUP BY brand_id
    """), {"m": market_id, "d": days}).fetchall()}


def _job_values(conn, market_id: int, *, new_only: bool
                ) -> Tuple[Dict[int, float], Optional[str]]:
    """Job counts from the same function the hiring drill-down uses.

    Deliberately not a ``COUNT(*)`` over the snapshot table. That count reads
    every listing ever observed, including ones the vendor has taken down, and
    it disagreed with the drill-down by 60 listings on this market.
    """
    listing = mlists.jobs(conn, market_id, page_size=1, include_all=True)
    wanted = ({"newly_observed"} if new_only
              else {"currently_observed", "newly_observed"})
    counts: Dict[int, float] = {}
    for row in listing.get("_all") or []:
        if row["status"] in wanted:
            bid = int(row["brand_id"])
            counts[bid] = counts.get(bid, 0.0) + 1
    meta = listing.get("meta") or {}
    return counts, ((meta.get("metric") or {}).get("collection") or {}
                    ).get("last_success_at")


def _funding_values(conn, market_id: int
                    ) -> Tuple[Dict[int, float], Dict[int, str]]:
    """Disclosed cumulative totals only.

    Undisclosed and bootstrapped vendors are not zero-funded vendors, so they
    are excluded rather than plotted at the bottom of the chart.
    """
    values: Dict[int, float] = {}
    unmeasured: Dict[int, str] = {}
    for bid, baseline in conn.execute(text("""
        SELECT mb.brand_id, mb.baseline FROM bw_market_brands mb
         WHERE mb.market_id = :m AND mb.role <> 'excluded'
    """), {"m": market_id}).fetchall():
        fund = ((baseline or {}).get("funding_baseline") or {}
                if isinstance(baseline, dict) else {})
        total = fund.get("total_musd")
        if isinstance(total, (int, float)):
            values[int(bid)] = float(total)
        else:
            unmeasured[int(bid)] = (
                "no disclosed total on file"
                + (f" — recorded as {fund.get('status')}"
                   if fund.get("status") else ""))
    return values, unmeasured


def _activity_values(conn, market: Dict[str, Any], days: int
                     ) -> Tuple[Dict[int, float], Dict[int, str]]:
    """The blended index, from the overview that publishes it."""
    overview = mpub.build_overview(conn, market, days=days)
    values: Dict[int, float] = {}
    unmeasured: Dict[int, str] = {}
    for row in overview.get("most_active") or []:
        bid = int(row["brand_id"])
        if row.get("activity_index") is None:
            unmeasured[bid] = (row.get("index_unavailable_because")
                               or "not measured on every channel")
        else:
            values[bid] = float(row["activity_index"])
    return values, unmeasured


def retains_last_good(collection: Dict[str, Any]) -> bool:
    """Whether a degraded source has a previous good reading worth keeping.

    "Failed or stale" is not a state name, it is a question about history: has
    this source ever succeeded? ``failed`` sits inside ``mmet.UNMEASURED``
    because a failed run measured nothing, and a source whose first run fails
    leaves genuinely no data — every vendor is unmeasured and that is correct.
    A source that fails after twenty good runs leaves twenty good readings, and
    dropping those would recompute the market's median from whichever vendors
    happened to refresh today, which is a property of the collectors and not of
    the market. The state name cannot tell the two apart. ``last_success_at``
    can, so it decides.
    """
    if collection.get("state") not in ("failed", "stale"):
        return False
    return bool((collection.get("freshness") or {}).get("last_success_at"))


def metric_values(conn, market: Dict[str, Any], metric_key: str, days: int
                  ) -> Dict[str, Any]:
    """Every eligible vendor's value for one metric, plus who is missing and why."""
    market_id = int(market["id"])
    eligible = _eligible(conn, market_id)
    spec = METRICS[metric_key]
    as_of: Optional[str] = None
    unmeasured: Dict[int, str] = {}

    if metric_key in ("headcount", "headcount_pct"):
        values, unmeasured, as_of = _headcount_values(
            conn, market_id, days, pct=metric_key == "headcount_pct")
    elif metric_key in ("posts", "mentions", "announcements"):
        values = _post_values(conn, market_id, days, kind=metric_key)
    elif metric_key in ("jobs_open", "jobs_new"):
        values, as_of = _job_values(conn, market_id,
                                    new_only=metric_key == "jobs_new")
    elif metric_key == "funding":
        values, unmeasured = _funding_values(conn, market_id)
    elif metric_key == "activity_index":
        values, unmeasured = _activity_values(conn, market, days)
    else:
        raise KeyError(metric_key)

    if metric_key == "mentions":
        # Earned mentions have no per-vendor policy row, because nothing polls
        # a vendor for them — they are matched out of the corpus the platform
        # already collected. `collection_state` therefore reads them as "not
        # configured", which would withhold every vendor's mention count on a
        # market that is measuring them fine.
        state = mmet.mentions_channel_state(conn, market_id)
        collection = {"state": state,
                      "label": mmet.STATE_LABELS.get(state, state),
                      "source": "corpus_match"}
    elif spec["source"] is None:
        collection = {"state": "healthy", "label": "Imported baseline",
                      "source": None}
    else:
        collection = mmet.collection_state(conn, market_id, spec["source"])

    # A vendor with no row in a count query genuinely published nothing, which
    # is a measurement — but only if collection reached it at all. Three cases,
    # and collapsing any two of them is the failure this module exists to stop.
    #
    # Never collected, not configured or still running: there is no last-good
    # value to fall back on, so the vendor leaves the cohort. Zero would be a
    # claim about a company nobody has read.
    #
    # Failed or stale: the stored rows are the last good reading. Keep them,
    # stamp the benchmark with the date collection last succeeded, and say so.
    # Recomputing from only the vendors that refreshed would move the median
    # for reasons that have nothing to do with the market (spec 4.16, MM-31).
    #
    # Healthy or partial: an absent row is an observed zero.
    degraded = retains_last_good(collection)
    last_success = (collection.get("freshness") or {}).get("last_success_at")
    if metric_key in ("posts", "mentions", "announcements",
                      "jobs_open", "jobs_new"):
        no_data = collection["state"] in mmet.UNMEASURED and not degraded
        for bid in eligible:
            if bid in values:
                continue
            if no_data:
                unmeasured[bid] = (
                    f"{spec['label'].lower()} could not be measured: "
                    f"{mmet.STATE_LABELS.get(collection['state'], collection['state'])}")
            else:
                values[bid] = 0.0
    if degraded:
        as_of = last_success

    values = {b: v for b, v in values.items() if b in eligible}
    unmeasured = {b: r for b, r in unmeasured.items()
                  if b in eligible and b not in values}
    return {"values": values, "unmeasured": unmeasured, "eligible": eligible,
            "collection": collection, "as_of": as_of, "spec": spec,
            "degraded": degraded}


# ---------------------------------------------------------------------------
# The comparison itself
# ---------------------------------------------------------------------------

def _pct_delta(value: float, base: float) -> Optional[float]:
    """A percentage difference, or nothing when the denominator is zero.

    A market median of zero is a real and common state early in a market's
    life. Dividing by it produces infinity, which renders as a very confident
    number, so the caller shows the absolute delta and says the percentage is
    unavailable instead.
    """
    if base == 0:
        return None
    return round((value - base) / abs(base) * 100, 1)


def compare(measured: Dict[str, Any], brand_id: int) -> Dict[str, Any]:
    """One vendor against the measured market and the Top N, from prepared values."""
    values: Dict[int, float] = measured["values"]
    eligible: Dict[int, str] = measured["eligible"]
    spec = measured["spec"]

    vendor_value = values.get(brand_id)
    peers = {b: v for b, v in values.items() if b != brand_id}
    peer_values = sorted(peers.values(), reverse=True)

    out: Dict[str, Any] = {
        "metric": {"key": next(k for k, v in METRICS.items() if v is spec),
                   **{f: v for f, v in spec.items() if f != "source"}},
        "vendor_id": brand_id,
        "vendor": eligible.get(brand_id),
        "vendor_value": vendor_value,
        "vendor_unmeasured_because": measured["unmeasured"].get(brand_id),
        "eligible_count": len(eligible),
        "measured_count": len(values),
        "market_peer_count": len(peers),
        "collection": measured["collection"],
        "as_of": measured["as_of"],
        "top_peer_count": 0,
        "top_label": None,
        "market_median": None, "market_average": None,
        "top_median": None, "top_average": None,
        "top_q1": None, "top_q3": None,
        "vendor_percentile": None,
        "delta_from_market_median": None,
        "percentage_delta_from_market_median": None,
        "delta_from_market_average": None,
        "delta_from_top_median": None,
        "percentage_delta_from_top_median": None,
        "suppressed": False,
        "degraded": bool(measured.get("degraded")),
        "notes": [],
    }
    if out["degraded"]:
        out["notes"].append(
            f"{measured['collection'].get('label') or 'Collection'} for this "
            f"metric is not current. These are the last good readings, as of "
            f"{measured['as_of'] or 'an unrecorded date'}, not a recalculation "
            f"from the vendors that did refresh.")

    if len(peers) < MIN_PEERS:
        out["suppressed"] = True
        out["notes"].append(
            f"Insufficient peer coverage. {len(peers)} of {len(eligible) - 1} "
            f"other vendors have a valid {spec['label'].lower()} for this "
            f"period, and {MIN_PEERS} are needed before a median or an average "
            f"says anything about the market.")
        return out

    top = peer_values[:TOP_N]
    out["top_peer_count"] = len(top)
    out["top_label"] = (f"Top {TOP_N} by {spec['label']}"
                        if len(top) >= TOP_N
                        else f"Top {len(top)} available")
    out["market_median"] = round(statistics.median(peer_values), 2)
    out["market_average"] = round(statistics.fmean(peer_values), 2)
    out["top_median"] = round(statistics.median(top), 2)
    out["top_average"] = round(statistics.fmean(top), 2)
    if len(top) >= 4:
        q = statistics.quantiles(top, n=4)
        out["top_q1"], out["top_q3"] = round(q[0], 2), round(q[2], 2)

    if vendor_value is None:
        out["notes"].append(
            f"Vendor not measured for this metric. "
            f"{out['vendor_unmeasured_because'] or 'No valid value on file.'}")
        return out

    # Rank against everyone, the vendor included: a percentile is a position in
    # the whole cohort, and excluding yourself from your own rank is incoherent.
    # Midrank, not "at or below". With "at or below", a market where every
    # vendor posted no new roles hands all of them the 100th percentile, which
    # reads as market-leading hiring and is really a market-wide zero. Midrank
    # puts a tied group at the middle of the ground it shares, so an all-zero
    # cohort comes out at 50 and nobody leads on a tie.
    whole = sorted(values.values())
    below = sum(1 for v in whole if v < vendor_value)
    at_or_below = sum(1 for v in whole if v <= vendor_value)
    out["vendor_percentile"] = round((below + at_or_below) / 2
                                     / len(whole) * 100)

    out["delta_from_market_median"] = round(vendor_value - out["market_median"], 2)
    out["percentage_delta_from_market_median"] = _pct_delta(
        vendor_value, out["market_median"])
    out["delta_from_market_average"] = round(
        vendor_value - out["market_average"], 2)
    out["delta_from_top_median"] = round(vendor_value - out["top_median"], 2)
    out["percentage_delta_from_top_median"] = _pct_delta(
        vendor_value, out["top_median"])
    for field, base in (("percentage_delta_from_market_median", "market median"),
                        ("percentage_delta_from_top_median", "top-cohort median")):
        if out[field] is None:
            out["notes"].append(
                f"Percentage comparison unavailable: the {base} is zero, so "
                f"only the absolute difference is shown.")
    return out


def benchmarks(conn, market: Dict[str, Any], brand_id: int, *,
               days: int = 30, metric_keys: Optional[List[str]] = None,
               include_cohort: bool = False) -> Dict[str, Any]:
    """The Benchmark view for one vendor, across the requested metrics.

    ``include_cohort`` decides whether the Top-N members are named. It is false
    for a restricted viewer, and the identities are then absent from the
    payload rather than hidden in the UI — a name that reaches the browser has
    been disclosed whatever the browser does with it.
    """
    eligible = _eligible(conn, int(market["id"]))
    if brand_id not in eligible:
        raise KeyError(f"vendor {brand_id} is not in this market")

    results = []
    for key in (metric_keys or list(METRICS)):
        if key not in METRICS:
            continue
        try:
            measured = metric_values(conn, market, key, days)
        except Exception:
            logger.exception("benchmark metric %s failed", key)
            continue
        row = compare(measured, brand_id)
        if include_cohort and not row["suppressed"]:
            ranked = sorted(((b, v) for b, v in measured["values"].items()
                             if b != brand_id), key=lambda p: -p[1])[:TOP_N]
            row["cohort"] = [{"brand_id": b, "vendor": eligible.get(b),
                              "value": v} for b, v in ranked]
        results.append(row)

    return {
        "market_id": int(market["id"]),
        "vendor_id": brand_id,
        "vendor": eligible.get(brand_id),
        "period_days": days,
        "cohort_named": include_cohort,
        "metrics": results,
        "note": ("More posts, funding or open roles is activity and scale, not "
                 "performance. A vendor above the market median is busier than "
                 "half the market on that channel, which is all this says."),
    }
