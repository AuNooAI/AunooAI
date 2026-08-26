"""What a number on the Market Monitor page means, and whether it was measured.

Every figure on that page used to be a bare integer. A vendor with no posts and
a vendor whose collection had never run both rendered as ``0``, and nothing on
screen separated them. That is the failure this module exists to prevent: a zero
is a measurement, and it may only be shown when a collector actually ran,
completed, and found nothing.

The state does not need new plumbing. ``bw_entity_source_policies`` already
carries, per vendor per source, whether the source can run at all
(``eligible`` / ``ineligible_reason``), when it last tried
(``last_attempt_at``), when it last worked (``last_success_at``), how often it
is meant to run (``cadence_seconds``) and whether it is currently failing
(``consecutive_failures``). ``bw_collection_runs`` carries the outcome of each
attempt. So the whole coverage contract is a read over two existing tables.

Two ideas are kept apart here, because conflating them is what made the old
page untrustworthy:

*   **Collection coverage** — how much of the market we successfully measured.
    Successful over eligible.
*   **Content volume** — how many qualifying items we found.

A percentage on its own hides which one it is, so every coverage block carries
its numerator and denominator and the UI is expected to show both.

Freshness comes from each source's own cadence, never a single global constant.
A profile collector on a weekly cadence and a post collector on a twelve-hour
one cannot share a staleness threshold; using one meant the weekly source read
as stale six days out of seven.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import text

from app.services import entity_scheduler as sch

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Where coverage comes from (spec 4.10)
# ---------------------------------------------------------------------------
#
# Content, platform and collection provider are three different things and the
# page used to blur them. Bright Data is a provider; LinkedIn is a platform;
# Xpoz is a provider whose items carry their own real platform. Reporting
# "Xpoz" as a platform made practitioner discussion on Bluesky look like a
# fourth network, and reporting "LinkedIn" as a provider implied we have a
# relationship with LinkedIn that we do not.
#
# Held as data rather than as markup so the live UI and the downloadable report
# cannot drift apart. Both render this list.
SOURCE_LEGEND: List[Dict[str, str]] = [
    {"key": "linkedin_company_post", "content": "Company posts",
     "platform": "LinkedIn", "provider": "Bright Data",
     "ownership": "vendor-owned",
     "dataset": "LinkedIn company posts"},
    {"key": "linkedin_company_profile", "content": "Company profiles and headcount",
     "platform": "LinkedIn", "provider": "Bright Data",
     "ownership": "vendor profile",
     "dataset": "LinkedIn company profiles"},
    {"key": "linkedin_jobs", "content": "Job listings",
     "platform": "LinkedIn", "provider": "Bright Data",
     "ownership": "vendor-associated",
     "dataset": "LinkedIn jobs"},
    {"key": "indeed_jobs", "content": "Job listings (experimental)",
     "platform": "Indeed", "provider": "Bright Data",
     "ownership": "vendor-associated; attribution unvalidated",
     "dataset": "Indeed jobs"},
    {"key": "xpoz_social", "content": "Practitioner discussion",
     "platform": "from item metadata", "provider": "Xpoz",
     "ownership": "third-party (earned)",
     "dataset": "social posts"},
    {"key": "bluesky", "content": "Practitioner discussion",
     "platform": "Bluesky", "provider": "Bluesky (direct)",
     "ownership": "third-party (earned)",
     "dataset": "posts"},
    {"key": "news", "content": "News",
     "platform": "the publication itself", "provider": "configured news/RSS feeds",
     "ownership": "third-party (earned)",
     "dataset": "articles"},
    {"key": "vendor_web", "content": "Vendor site updates",
     "platform": "vendor website / RSS", "provider": "site and RSS collector",
     "ownership": "vendor-owned",
     "dataset": "pages"},
    {"key": "ats_jobs", "content": "Job listings",
     "platform": "the company's own hiring system",
     "provider": "the hiring system's public job board API",
     "ownership": "vendor-associated",
     "dataset": "job board postings"},
    {"key": "ats_discovery", "content": "Finding a vendor's hiring system",
     "platform": "vendor website", "provider": "site collector",
     "ownership": "vendor-owned",
     "dataset": "careers page"},
    {"key": "vendor_web_discovery", "content": "Finding a vendor's feed",
     "platform": "vendor website", "provider": "site and RSS collector",
     "ownership": "vendor-owned",
     "dataset": "feed discovery"},
    {"key": "pitchbook_company", "content": "Funding and ownership",
     "platform": "PitchBook", "provider": "Bright Data",
     "ownership": "third-party company data",
     "dataset": "PitchBook companies"},
    {"key": "zoominfo_company", "content": "Company profile and contacts",
     "platform": "ZoomInfo", "provider": "Bright Data",
     "ownership": "third-party company data",
     "dataset": "ZoomInfo companies"},
    {"key": "crunchbase_company", "content": "Funding stages, investors and scores",
     "platform": "Crunchbase", "provider": "Bright Data",
     "ownership": "third-party company data",
     "dataset": "Crunchbase companies"},
    {"key": "workbook", "content": "Disclosed funding totals",
     "platform": "imported workbook", "provider": "operator import",
     "ownership": "third-party company data",
     "dataset": "vendor baseline"},
]

_LEGEND_BY_KEY = {row["key"]: row for row in SOURCE_LEGEND}


def legend_for(source: str) -> Dict[str, str]:
    """Platform, provider and ownership for one source key.

    Falls back to naming the source rather than guessing a platform. An unknown
    source with "LinkedIn" filled in by default is worse than one that admits
    it is unlabelled.
    """
    row = _LEGEND_BY_KEY.get(source)
    if row:
        return dict(row)
    return {"key": source, "content": source, "platform": "unknown",
            "provider": "unknown", "ownership": "unknown", "dataset": source}


# ---------------------------------------------------------------------------
# Data states (spec 3)
# ---------------------------------------------------------------------------

# Numeric zero is only one of these, and only ever the one that was measured.
STATES = ("observed_zero", "healthy", "not_configured", "never_collected",
          "collecting", "partial", "stale", "failed")

# Plain-language rendering, so the UI and the HTML report cannot describe the
# same state in two different ways.
STATE_LABELS: Dict[str, str] = {
    "observed_zero": "none found",
    "healthy": "measured",
    "not_configured": "no source configured",
    "never_collected": "never collected",
    "collecting": "collecting now",
    "partial": "partly collected",
    "stale": "out of date",
    "failed": "collection failed",
}

# Which states mean "this number is not a measurement". A caller rendering a
# figure consults this rather than re-deriving the rule; the old code had the
# test written four different ways in four places.
UNMEASURED = frozenset({"not_configured", "never_collected", "collecting",
                        "failed"})


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _cadence_seconds(source: str, rows: List[Dict[str, Any]]) -> int:
    """The cadence this source actually runs on.

    Prefers what the policy rows say, because an operator can change a single
    vendor's cadence and the freshness threshold should follow it. Falls back to
    the source default.
    """
    stated = [int(r["cadence_seconds"]) for r in rows
              if r.get("cadence_seconds")]
    if stated:
        return min(stated)
    return sch.CADENCE_HOURS.get(source, 24) * 3600


def tracked_sources() -> List[str]:
    """The sources a market panel should report on, in reading order.

    Scheduled sources first, because those are the ones a zero can legitimately
    come from. The manual-only ones follow so a reader can see they exist and
    why they are not running, rather than wondering whether we simply forgot
    them.
    """
    return list(sch.SCHEDULED_SOURCES) + sorted(sch.MANUAL_ONLY_SOURCES)


def collection_state(conn, market_id: int, source: str) -> Dict[str, Any]:
    """Whether ``source`` measured this market, and how much of it.

    Returns the coverage block from spec section 3 together with a state that
    is *not* value-dependent: this function does not know what was counted, so
    it never returns ``observed_zero``. Combine it with the observed value
    through :func:`resolve` to get the state a card should render.
    """
    policies = [dict(r) for r in conn.execute(text("""
        SELECT p.brand_id, p.enabled, p.eligible, p.ineligible_reason,
               p.cadence_seconds, p.last_attempt_at, p.last_success_at,
               p.consecutive_failures, p.claimed_at
          FROM bw_entity_source_policies p
          JOIN bw_market_brands mb ON mb.brand_id = p.brand_id
         WHERE mb.market_id = :m AND mb.role <> 'excluded'
           AND p.source = :s
    """), {"m": market_id, "s": source}).mappings().all()]

    registry_total = conn.execute(text("""
        SELECT COUNT(*) FROM bw_market_brands
         WHERE market_id = :m AND role <> 'excluded'
    """), {"m": market_id}).scalar() or 0

    eligible_rows = [r for r in policies if r["eligible"] and r["enabled"]]
    eligible = len(eligible_rows)
    attempted = sum(1 for r in eligible_rows if r["last_attempt_at"])
    successful = sum(1 for r in eligible_rows if r["last_success_at"])
    in_flight = sum(1 for r in eligible_rows if r["claimed_at"])

    last_success = max((r["last_success_at"] for r in eligible_rows
                        if r["last_success_at"]), default=None)
    cadence = _cadence_seconds(source, policies)
    # Two missed intervals, not one. A collector that runs every twelve hours
    # and is thirteen hours late has not failed; calling that stale trains the
    # reader to ignore the badge.
    stale_after = (last_success + timedelta(seconds=cadence * 2)
                   if last_success else None)
    is_stale = bool(stale_after and stale_after < _now())

    # The most recent run for this market and source, for the failed state and
    # for the error the panel shows.
    latest = conn.execute(text("""
        SELECT status, error, error_code, completed_at, started_at,
               records_received, records_new
          FROM bw_collection_runs
         WHERE market_id = :m AND source = :s
         ORDER BY started_at DESC LIMIT 1
    """), {"m": market_id, "s": source}).mappings().first()
    latest = dict(latest) if latest else None

    scheduled = (source not in sch.MANUAL_ONLY_SOURCES
                 and source not in sch.PAUSED_SOURCES)

    if eligible == 0:
        # Nothing in this market can be collected from this source. Usually a
        # missing identifier, which is worth saying rather than reporting as a
        # failure somebody is meant to fix in the collector.
        reasons = sorted({r["ineligible_reason"] for r in policies
                          if r.get("ineligible_reason")})
        state = "not_configured"
        # A source that is manual-only by policy is not misconfigured, and the
        # reason it cannot be scheduled is the useful thing to say. Reporting
        # Indeed as "no vendor has the required identifier" sends the reader
        # looking for an identifier that does not exist.
        detail = (sch.MANUAL_ONLY_REASONS.get(source)
                  or sch.PAUSED_SOURCES.get(source)
                  or "; ".join(reasons)
                  or (f"no vendor in this market has a "
                      f"{sch.REQUIRED_IDENTIFIER.get(source, 'required identifier')}"))
    elif in_flight and successful == 0:
        state, detail = "collecting", "a run is in progress"
    elif successful == 0 and latest and latest["status"] == "failed":
        state, detail = "failed", (latest.get("error_code")
                                   or latest.get("error") or "the last run failed")
    elif successful == 0:
        state, detail = "never_collected", (
            "configured, but no run has succeeded yet")
    elif successful < eligible:
        state = "partial"
        detail = f"{successful} of {eligible} vendors collected"
    elif is_stale:
        state = "stale"
        detail = (f"last successful collection "
                  f"{_ago(last_success)}, expected every {_every(cadence)}")
    else:
        state, detail = "healthy", None

    return {
        "source": source,
        "state": state,
        "state_detail": detail,
        "scheduled": scheduled,
        "coverage": {
            "registry_total": int(registry_total),
            "eligible": eligible,
            "attempted": attempted,
            "successful": successful,
            "pct_of_eligible": (round(successful / eligible * 100, 1)
                                if eligible else None),
            "label": (f"{successful} of {eligible} vendors"
                      if eligible else "no vendor is configured for this source"),
        },
        "freshness": {
            "last_success_at": _iso(last_success),
            "expected_interval_seconds": cadence,
            "stale_after": _iso(stale_after),
            "is_stale": is_stale,
        },
        "latest_run": ({
            "status": latest["status"],
            "error_code": latest.get("error_code"),
            "records_received": latest.get("records_received"),
            "started_at": _iso(latest.get("started_at")),
            "completed_at": _iso(latest.get("completed_at")),
        } if latest else None),
    }


def resolve(collection: Dict[str, Any], value: Optional[float]) -> str:
    """The state a card should render, given what collection did and what it found.

    This is the one rule the whole module exists for: a zero is only a zero when
    collection succeeded across the stated population. Everything else that
    looks like nothing is reported as what it actually is.
    """
    state = collection.get("state", "never_collected")
    if state != "healthy":
        return state
    if value is None:
        return "never_collected"
    return "observed_zero" if not value else "healthy"


def _iso(value: Optional[datetime]) -> Optional[str]:
    return value.isoformat() if isinstance(value, datetime) else None


def _every(seconds: int) -> str:
    hours = seconds / 3600
    if hours < 1:
        return f"{int(seconds / 60)} minutes"
    if hours < 48:
        return f"{int(hours)} hours"
    return f"{int(hours / 24)} days"


def _ago(when: Optional[datetime]) -> str:
    if not when:
        return "never"
    seconds = (_now() - when).total_seconds()
    if seconds < 3600:
        return f"{int(seconds / 60)} minutes ago"
    if seconds < 172800:
        return f"{int(seconds / 3600)} hours ago"
    return f"{int(seconds / 86400)} days ago"


# ---------------------------------------------------------------------------
# The metric envelope (spec 3)
# ---------------------------------------------------------------------------

def metric(metric_id: str, *, label: str, definition: str,
           numerator: str, denominator: Optional[str] = None,
           window: Optional[Dict[str, Any]] = None,
           collection: Optional[Dict[str, Any]] = None,
           collections: Optional[List[Dict[str, Any]]] = None,
           value: Optional[float] = None,
           limitations: Optional[List[str]] = None) -> Dict[str, Any]:
    """Assemble the metadata block that must travel with every figure.

    Accepts either one ``collection`` state or several. A metric fed by more
    than one source takes the worst state of its inputs, because a market total
    whose news half failed is not healthy just because its LinkedIn half worked.
    """
    states = [c for c in ([collection] if collection else []) + (collections or [])
              if c]
    # Worst-first: anything that is not a measurement outranks a measurement,
    # and among measurements, partial and stale outrank healthy.
    order = ["failed", "never_collected", "not_configured", "collecting",
             "partial", "stale", "healthy"]
    worst = min((c["state"] for c in states),
                key=lambda s: order.index(s) if s in order else 0,
                default="never_collected")
    combined = dict(states[0]) if len(states) == 1 else {"state": worst}
    data_state = resolve({"state": worst}, value)

    sources = []
    for c in states:
        leg = legend_for(c["source"])
        sources.append({
            "provider": leg["provider"],
            "dataset": leg["dataset"],
            "platform": leg["platform"],
            "ownership": leg["ownership"],
            "status": c["state"],
            "last_success_at": c["freshness"]["last_success_at"],
            "expected_interval_seconds":
                c["freshness"]["expected_interval_seconds"],
            "records_observed": (c.get("latest_run") or {}).get("records_received"),
            # Provider caps are recorded per run when a batch comes back at the
            # limit. Absent means not truncated, not unknown.
            "truncated": bool((c.get("latest_run") or {}).get("truncated")),
        })

    return {
        "metric_id": metric_id,
        "label": label,
        "definition": definition,
        "numerator": numerator,
        "denominator": denominator,
        "window": window,
        "as_of": _iso(_now()),
        "data_state": data_state,
        "data_state_label": STATE_LABELS.get(data_state, data_state),
        "measured": data_state not in UNMEASURED,
        "state_detail": combined.get("state_detail"),
        "sources": sources,
        "coverage": (states[0]["coverage"] if len(states) == 1 else None),
        "freshness": (states[0]["freshness"] if len(states) == 1 else None),
        "limitations": limitations or [],
    }
