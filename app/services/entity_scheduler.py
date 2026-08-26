"""Which vendors to collect next, remembered in the database.

The collector took the first twenty vendors by ``sort_order`` on every pass.
There are eighty-three, so the same nineteen were refreshed indefinitely and
sixty-four had never been collected from a live source at all — their only data
was the April workbook import. The cap was not the problem; the absence of a
cursor was.

Selection state lives in ``bw_entity_source_policies``, one row per
``(brand_id, source)``, because it has to survive a restart and be shared by
overlapping scheduler passes. An in-memory cursor would reset on every deploy
and two passes would pick the same vendors.

The ordering is: due first, then never-collected before long-ago-collected,
then priority, then the brand id so the answer is stable. The cap is applied
**after** that selection, never before — applying it first is what produced a
fixed prefix.

Eligibility is per source, not global. Asking Bright Data for a LinkedIn
profile for a vendor with no LinkedIn URL on file spends a request to be told
nothing, and it also makes the coverage numbers lie: a vendor that can never be
collected from a source should not sit in that source's backlog forever looking
overdue.

Cadence is per entity, not per market. A vendor in two markets is one company
and gets collected once; the shortest cadence any membership asks for wins, and
``derived_from`` records which memberships produced the policy so switching one
market off cannot stop collection another market still needs.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import text

logger = logging.getLogger(__name__)

# Sources that may never run on a schedule. PitchBook and ZoomInfo need a URL
# an operator entered by hand, and Indeed's employer attribution has never been
# checked against a live response. They are refused at admission rather than
# merely left out of the cadence list, because a queued market-wide request was
# still being claimed and then failed as undispatched — one failed run per
# source per scheduler cycle, drowning real failures.
MANUAL_ONLY_SOURCES = frozenset({
    'pitchbook_company', 'zoominfo_company', 'indeed_jobs',
})

# Why each one is manual-only, in words a reader can act on. Kept beside the
# set rather than in a comment, because the health panel reported these as
# "failing" on a stranded run from before the policy existed and had nothing
# truer to show.
MANUAL_ONLY_REASONS: Dict[str, str] = {
    'pitchbook_company': (
        'needs a pitchbook_url an operator entered by hand — unlike Crunchbase '
        'there is no slug to guess from the company name'
    ),
    'zoominfo_company': (
        'needs a zoominfo_url an operator entered by hand — unlike Crunchbase '
        'there is no slug to guess from the company name'
    ),
    'indeed_jobs': (
        "attribution works, but every search is billed and needs a location. "
        "keyword_search takes the company name and each listing is kept only "
        "when the employer Indeed reports contains every word of the vendor's "
        "name — posted_by is a closed enum of poster types and is not the "
        "employer filter it looks like. Left manual because the dataset has no "
        "'anywhere' location, so a vendor hiring in several countries needs one "
        "paid input per location."
    ),
}

# Sources temporarily withheld from automatic dispatch, with the reason. These
# are not manual-only by policy; they are broken and honest about it.
#
# linkedin_jobs was listed here on 25 August for an HTTP 400 naming the wrong
# discovery collector id. That request shape had been corrected on 20 August
# (see LinkedInDatasetClient.trigger_jobs, discover_by=keyword with company as
# its own input field) and the source had succeeded six times running before
# the pause was written. The entry was reading the three failed rows from the
# morning of the 20th as current state. Removed, because a pause whose stated
# reason no longer holds silences a working source and reads as a broken one.
#
# Before adding an entry here: check the most recent run of that source, not
# the most alarming one.
PAUSED_SOURCES: Dict[str, str] = {}

# Effective cadence per source, in hours.
CADENCE_HOURS: Dict[str, int] = {
    'linkedin_company_post': 12,
    'linkedin_company_profile': 168,
    'linkedin_jobs': 72,
    'crunchbase_company': 168,
    'vendor_web': 12,
    'vendor_web_discovery': 168,
    # The company's own hiring system. Free and unauthenticated, so this can
    # run more often than the billed LinkedIn jobs dataset — daily is enough
    # for a job board and keeps the newly/no-longer-observed comparison
    # meaningful without hammering somebody else's API.
    'ats_jobs': 24,
    # Which system a company uses changes when it migrates, which is rare.
    'ats_discovery': 336,
}

# The identifier a source cannot run without.
REQUIRED_IDENTIFIER: Dict[str, str] = {
    'linkedin_company_post': 'linkedin_company_url',
    'linkedin_company_profile': 'linkedin_company_url',
    'linkedin_jobs': 'linkedin_company_url',
    'crunchbase_company': 'crunchbase_url',
    'vendor_web': 'domain',
    'vendor_web_discovery': 'domain',
    'pitchbook_company': 'pitchbook_url',
    'zoominfo_company': 'zoominfo_url',
    # Discovery needs somewhere to look; collection needs the board discovery
    # found. Keeping them separate means a vendor with no board sits out of the
    # collection backlog instead of looking permanently overdue.
    'ats_discovery': 'domain',
    'ats_jobs': 'ats_board',
}

SCHEDULED_SOURCES = tuple(CADENCE_HOURS)

# A claim older than this belonged to a pass that died. Reclaimable.
CLAIM_TIMEOUT = timedelta(hours=2)

# Failure backoff, doubling, so a vendor the provider cannot process backs off
# instead of consuming a slot on every pass.
BACKOFF_BASE = timedelta(hours=1)
BACKOFF_MAX = timedelta(days=7)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def max_vendors_per_run() -> int:
    try:
        return max(1, int(os.getenv('MARKET_MAX_VENDORS_PER_RUN', '20')))
    except ValueError:
        return 20


# ---------------------------------------------------------------------------
# Seeding and reconciliation
# ---------------------------------------------------------------------------

def seed_policies(conn, source: Optional[str] = None) -> Dict[str, Any]:
    """Create or refresh one policy per eligible (brand, source).

    Idempotent, and safe to run on every deploy. Eligibility is recomputed
    each time because identifiers get added: a vendor that had no LinkedIn URL
    last week becomes collectable the moment somebody enters one.
    """
    sources = [source] if source else list(SCHEDULED_SOURCES)
    summary: Dict[str, Any] = {'sources': {}, 'created': 0, 'updated': 0}

    for src in sources:
        cadence = CADENCE_HOURS.get(src)
        if cadence is None:
            continue
        identifier_kind = REQUIRED_IDENTIFIER.get(src)

        rows = conn.execute(text("""
            SELECT mb.brand_id,
                   bool_or(mb.collection_enabled) AS wanted,
                   array_agg(DISTINCT mb.market_id) AS markets,
                   EXISTS (SELECT 1 FROM bw_vendor_identifiers i
                            WHERE i.brand_id = mb.brand_id
                              AND i.kind = :kind AND i.valid_to IS NULL)
                       AS has_identifier
              FROM bw_market_brands mb
             WHERE mb.role <> 'excluded'
             GROUP BY mb.brand_id
        """), {'kind': identifier_kind or ''}).mappings().all()

        created = updated = eligible = 0
        for row in rows:
            ok = bool(row['has_identifier']) if identifier_kind else True
            reason = (None if ok
                      else f'no active {identifier_kind} identifier on file')
            eligible += 1 if ok else 0
            result = conn.execute(text("""
                INSERT INTO bw_entity_source_policies
                    (brand_id, source, enabled, cadence_seconds, priority,
                     eligible, ineligible_reason, derived_from, next_due_at)
                VALUES (:b, :s, :enabled, :cadence, 50, :eligible, :reason,
                        CAST(:derived AS JSONB), NULL)
                ON CONFLICT (brand_id, source) DO UPDATE
                   SET enabled = EXCLUDED.enabled,
                       -- Shortest cadence any membership asks for wins.
                       cadence_seconds = LEAST(
                           bw_entity_source_policies.cadence_seconds,
                           EXCLUDED.cadence_seconds),
                       eligible = EXCLUDED.eligible,
                       ineligible_reason = EXCLUDED.ineligible_reason,
                       derived_from = EXCLUDED.derived_from,
                       updated_at = NOW()
                RETURNING (xmax = 0) AS created
            """), {'b': row['brand_id'], 's': src,
                   'enabled': bool(row['wanted']),
                   'cadence': cadence * 3600, 'eligible': ok,
                   'reason': reason,
                   'derived': json.dumps(
                       {'markets': [int(m) for m in row['markets']],
                        'requires': identifier_kind})}).mappings().first()
            if result and result['created']:
                created += 1
            else:
                updated += 1

        summary['sources'][src] = {'policies': len(rows), 'eligible': eligible,
                                   'created': created, 'updated': updated}
        summary['created'] += created
        summary['updated'] += updated
    return summary


def reconcile_from_history(conn, source: Optional[str] = None) -> int:
    """Set last_success_at from snapshots we already hold.

    Without this, seeding would mark every vendor as never collected and the
    first sweep would re-fetch the twenty already collected yesterday. A vendor
    with no snapshot stays null and is therefore immediately due, which is
    correct — it has never been collected.
    """
    sources = [source] if source else list(SCHEDULED_SOURCES)
    updated = conn.execute(text("""
        UPDATE bw_entity_source_policies p
           SET last_success_at = s.newest,
               next_due_at = s.newest + make_interval(secs => p.cadence_seconds),
               updated_at = NOW()
          FROM (SELECT brand_id, source, max(observed_at) AS newest
                  FROM bw_vendor_snapshots
                 WHERE source = ANY(:sources)
                 GROUP BY brand_id, source) s
         WHERE p.brand_id = s.brand_id AND p.source = s.source
           AND (p.last_success_at IS DISTINCT FROM s.newest
                -- Also repair a row whose success time is right but whose due
                -- time was never derived from it, or was cleared. Skipping
                -- those left recently-collected vendors reading as due.
                OR p.next_due_at IS NULL)
    """), {'sources': sources}).rowcount
    return int(updated or 0)


# ---------------------------------------------------------------------------
# Selection
# ---------------------------------------------------------------------------

def claim_due(conn, source: str, limit: Optional[int] = None,
              claimed_by: Optional[str] = None) -> List[int]:
    """Claim the next batch of vendors due for this source.

    ``FOR UPDATE SKIP LOCKED`` plus a persisted claim, so two overlapping
    scheduler passes cannot take the same vendor. The cap is applied here,
    after due-and-eligible filtering, so a full sweep completes over
    successive passes instead of re-reading a fixed prefix.
    """
    if source in MANUAL_ONLY_SOURCES:
        raise ValueError(f'{source} is manual-only and is never scheduled')
    if source in PAUSED_SOURCES:
        return []

    cap = limit if limit is not None else max_vendors_per_run()
    stale_claim = _now() - CLAIM_TIMEOUT

    rows = conn.execute(text("""
        WITH due AS (
            SELECT id FROM bw_entity_source_policies
             WHERE source = :source AND enabled AND eligible
               AND (next_due_at IS NULL OR next_due_at <= NOW())
               AND (claimed_at IS NULL OR claimed_at < :stale)
             ORDER BY next_due_at NULLS FIRST,
                      last_success_at NULLS FIRST,
                      priority DESC,
                      brand_id
             LIMIT :cap
             FOR UPDATE SKIP LOCKED
        )
        UPDATE bw_entity_source_policies p
           SET claimed_at = NOW(), claimed_by = :who,
               last_attempt_at = NOW(), updated_at = NOW()
          FROM due WHERE p.id = due.id
        RETURNING p.brand_id
    """), {'source': source, 'cap': cap, 'stale': stale_claim,
           'who': claimed_by or 'scheduler'}).fetchall()
    return [int(r[0]) for r in rows]


def record_success(conn, source: str, brand_ids: List[int]) -> int:
    """Advance the vendors a provider actually processed.

    Called for a successful batch even when it returned no records: the
    provider was asked and answered, so those vendors are done for this
    cadence. Leaving them due would put the same batch up again forever.
    """
    if not brand_ids:
        return 0
    return int(conn.execute(text("""
        UPDATE bw_entity_source_policies
           SET last_success_at = NOW(),
               next_due_at = NOW() + make_interval(secs => cadence_seconds),
               claimed_at = NULL, claimed_by = NULL,
               consecutive_failures = 0, last_error = NULL, updated_at = NOW()
         WHERE source = :s AND brand_id = ANY(:ids)
    """), {'s': source, 'ids': brand_ids}).rowcount or 0)


def record_failure(conn, source: str, brand_ids: List[int],
                   error: Optional[str] = None) -> int:
    """Back a failing vendor off instead of letting it consume a slot forever.

    ``last_success_at`` is deliberately untouched: the vendor's data is as old
    as it was, and pretending otherwise would hide staleness behind a failure.
    """
    if not brand_ids:
        return 0
    return int(conn.execute(text("""
        UPDATE bw_entity_source_policies
           SET consecutive_failures = consecutive_failures + 1,
               last_error = :err,
               claimed_at = NULL, claimed_by = NULL,
               next_due_at = NOW() + LEAST(
                   make_interval(secs => :base * POWER(2,
                       LEAST(consecutive_failures, 10))),
                   make_interval(secs => :cap)),
               updated_at = NOW()
         WHERE source = :s AND brand_id = ANY(:ids)
    """), {'s': source, 'ids': brand_ids, 'err': (error or '')[:500] or None,
           'base': int(BACKOFF_BASE.total_seconds()),
           'cap': int(BACKOFF_MAX.total_seconds())}).rowcount or 0)


def release_claims(conn, source: str, brand_ids: List[int]) -> None:
    """Drop claims without advancing anything, for an aborted dispatch."""
    if not brand_ids:
        return
    conn.execute(text("""
        UPDATE bw_entity_source_policies
           SET claimed_at = NULL, claimed_by = NULL, updated_at = NOW()
         WHERE source = :s AND brand_id = ANY(:ids)
    """), {'s': source, 'ids': brand_ids})


# ---------------------------------------------------------------------------
# Admission
# ---------------------------------------------------------------------------

def admit_request(conn, source: str, brand_id: Optional[int]) -> None:
    """Refuse a request that cannot possibly work, before a run is opened.

    A market-wide PitchBook request used to be accepted, open a run, claim it,
    and then fail as undispatched — one failed run per scheduler cycle for
    three sources, which is noise that hides real failures. Refusing at
    admission means the run is never created.
    """
    if source in MANUAL_ONLY_SOURCES:
        if brand_id is None:
            raise ValueError(
                f'{source} is manual-only: request it for one vendor, not for '
                f'the whole market')
        kind = REQUIRED_IDENTIFIER.get(source)
        if kind:
            has = conn.execute(text("""
                SELECT 1 FROM bw_vendor_identifiers
                 WHERE brand_id = :b AND kind = :k AND valid_to IS NULL
            """), {'b': brand_id, 'k': kind}).scalar()
            if not has:
                raise ValueError(
                    f'{source} needs an operator-supplied {kind} for this '
                    f'vendor before it can be requested')
    if source in PAUSED_SOURCES and brand_id is None:
        raise ValueError(f'{source} is paused: {PAUSED_SOURCES[source]}')


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------

def coverage(conn, source: Optional[str] = None) -> List[Dict[str, Any]]:
    """Per source: eligible, never collected, due, overdue, disabled."""
    rows = conn.execute(text("""
        SELECT source,
               count(*) AS policies,
               count(*) FILTER (WHERE enabled AND eligible) AS collectable,
               count(*) FILTER (WHERE NOT eligible) AS ineligible,
               count(*) FILTER (WHERE NOT enabled) AS disabled,
               count(*) FILTER (WHERE enabled AND eligible
                                AND last_success_at IS NULL) AS never_collected,
               count(*) FILTER (WHERE enabled AND eligible
                                AND (next_due_at IS NULL
                                     OR next_due_at <= NOW())) AS due_now,
               count(*) FILTER (WHERE claimed_at IS NOT NULL) AS claimed,
               count(*) FILTER (WHERE consecutive_failures > 0) AS failing
          FROM bw_entity_source_policies
         WHERE (:source IS NULL OR source = :source)
         GROUP BY source ORDER BY source
    """), {'source': source}).mappings().all()
    return [dict(r) for r in rows]
