"""Events, and how much anybody should believe them.

An event here is a claim that something happened, carried with the evidence for
it and an explicit statement of who is making it. The qualification is the
point. A vendor announcing its own funding round is real information and is not
the same as two independent outlets reporting it, and a system that renders
both as "funding round, 14 August" has thrown away the only thing that
distinguished them.

So corroboration is counted in **distinct sources**, never in evidence rows.
Ten outlets syndicating one wire story share an independence key and count
once. This is the difference between "widely reported" and "widely copied", and
row-counting cannot tell them apart.

The ladder runs: a company's own post is a ``vendor_claim``; one unconnected
source makes it ``single_source``; two make it ``corroborated``; a filing or
other primary document makes it ``primary_document``. Evidence that contradicts
the event does not delete it — the event stays visible and goes to
``pending_review``, because a disputed event that disappears looks exactly like
one that never happened.

Dedupe is by fingerprint: type, subjects, the attributes that make the event
what it is, and the date bucket. A retried callback, a re-run backfill and a
second outlet reporting the same round all land on the same fingerprint, so
they merge evidence and raise corroboration instead of creating three events.

An event whose date nobody stated keeps a null date and ``date_precision =
'unknown'``. The date we happened to extract it is not the date it happened.
"""

from __future__ import annotations

import hashlib
import re
import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional
from urllib.parse import urlsplit

from sqlalchemy import text

logger = logging.getLogger(__name__)

# Bump this when an extractor's *output for the same event* improves — a better
# headline, a fuller description. The upsert below refreshes title and
# description when the incoming version is newer than the stored one, and
# leaves them alone otherwise, so a re-run at the same version never churns.
#
# 1.1: owned-post events were titled from the post's opening line, so a real
# Booz Allen Hamilton partnership read "Security operations are being asked to
# move at machine speed" and named neither the partner nor the partnership.
# 1.2: rejected headlines that point at the news instead of stating it — "Read
# the logic behind...", "dive into the details of our official announcement
# below" — which matched a kind marker and then deferred.
EXTRACTION_VERSION = '1.2'

EVENT_TYPES = (
    'funding_round', 'acquisition', 'operating_status_change',
    'leadership_change', 'product_launch', 'pricing_change', 'partnership',
    'customer_win', 'geographic_expansion', 'headcount_change',
    'hiring_spike', 'brand_identity_change', 'controversy',
    'regulatory_legal', 'narrative_spike',
)

# Ordered weakest to strongest, so an upgrade is a comparison.
CORROBORATION_ORDER = ('uncorroborated', 'vendor_claim', 'single_source',
                       'corroborated', 'primary_document')


def _now() -> datetime:
    return datetime.now(timezone.utc)


def date_bucket(occurred_at: Optional[datetime],
                precision: str = 'day') -> str:
    """The part of the date that identifies the event.

    Two reports of one funding round rarely agree to the minute and usually
    agree on the day, so the day is what the fingerprint uses. An undated
    event buckets as 'unknown', which means every undated event of the same
    type about the same company is treated as the same event — deliberately,
    because creating a new one per sighting would multiply a single rumour.
    """
    if occurred_at is None:
        return 'unknown'
    if precision == 'month':
        return occurred_at.strftime('%Y-%m')
    return occurred_at.strftime('%Y-%m-%d')


def fingerprint(*, event_type: str, brand_ids: Iterable[int],
                attributes: Optional[Dict[str, Any]] = None,
                occurred_at: Optional[datetime] = None,
                precision: str = 'day') -> str:
    """Identity of an event, independent of who reported it or when."""
    payload = json.dumps({
        'type': event_type,
        'subjects': sorted(int(b) for b in brand_ids),
        'attrs': attributes or {},
        'date': date_bucket(occurred_at, precision),
    }, sort_keys=True, separators=(',', ':'), default=str)
    return hashlib.sha256(payload.encode('utf-8')).hexdigest()


# Sources that carry the company's own words. A job advert, a page on the
# company's own site and a self-written LinkedIn profile are all the company
# speaking, whichever platform delivered them, so they are one voice and not
# independent confirmation of anything.
SELF_REPORTED_SOURCES = frozenset({
    'vendor_web', 'linkedin_jobs', 'linkedin_company_profile', 'workbook',
})

# Only a filing or equivalent record counts as a primary document. Nothing in
# this tenant produces one yet, so the top rung stays empty rather than being
# reached by a vendor's own press page.
PRIMARY_DOCUMENT_PREFIXES = ('official:', 'filing:', 'sec:')


def independence_key_for_source(source: str) -> str:
    """One key per voice, with self-reported sources marked as owned."""
    if source in SELF_REPORTED_SOURCES:
        return f'owned:{source}'
    return f'source:{source}'


def independence_key_for_article(news_source: Optional[str],
                                 url: Optional[str] = None,
                                 bias_source: Optional[str] = None,
                                 owned_domains: Optional[Dict[str, str]] = None
                                 ) -> str:
    """What counts as one source.

    The publisher's domain, so syndicated copies collapse. A vendor's own
    channel is keyed to the vendor, so its blog and its LinkedIn are one voice
    rather than two.

    ``bias_source`` alone was not enough to establish that. Dropzone AI's blog
    posts are stored with an empty ``bias_source``, so eleven of them keyed as
    ``domain:dropzone.ai`` — an independent publisher. Pair that with the
    vendor's LinkedIn post about the same launch and the event would have read
    as *corroborated*: the company confirming itself, presented as two sources
    agreeing. Manufactured consensus is the thing this system exists to detect,
    so producing it internally is the worst available failure.

    ``owned_domains`` maps a host to the vendor that owns it, from the registry's
    own ``domain`` identifiers. A host in that map is the vendor speaking
    whatever the record says.
    """
    if (bias_source or '').startswith('vendor:'):
        return f"owned:{bias_source}"
    if url:
        host = (urlsplit(url).netloc or '').lower()
        if host.startswith('www.'):
            host = host[4:]
        if host:
            owner = (owned_domains or {}).get(host)
            if owner:
                return f"owned:vendor:{owner}"
            return f"domain:{host}"
    return f"source:{(news_source or 'unknown').lower()}"


def owned_domains(conn, market_id: Optional[int] = None) -> Dict[str, str]:
    """Host to owning vendor, for every monitored company's own site.

    Read from the registry rather than guessed from a name, so a company whose
    domain does not resemble its display name is still recognised as itself.
    """
    sql = """
        SELECT i.normalized_value AS host, b.display_name
          FROM bw_vendor_identifiers i
          JOIN bw_brands b ON b.id = i.brand_id
         WHERE i.kind = 'domain' AND i.valid_to IS NULL
    """
    params: Dict[str, Any] = {}
    if market_id is not None:
        sql += """ AND EXISTS (SELECT 1 FROM bw_market_brands mb
                                WHERE mb.brand_id = i.brand_id
                                  AND mb.market_id = :m)"""
        params['m'] = market_id
    out: Dict[str, str] = {}
    for row in conn.execute(text(sql), params).mappings():
        host = (row['host'] or '').strip().lower()
        if host.startswith('www.'):
            host = host[4:]
        if host:
            out[host] = row['display_name']
    return out


# ---------------------------------------------------------------------------
# Writing events
# ---------------------------------------------------------------------------

def upsert_event(conn, *, event_type: str, title: str, description: str,
                 brand_ids: Dict[int, str],
                 attributes: Optional[Dict[str, Any]] = None,
                 occurred_at: Optional[datetime] = None,
                 precision: str = 'day',
                 published_at: Optional[datetime] = None,
                 confidence: Optional[float] = None,
                 subtype: Optional[str] = None) -> Dict[str, Any]:
    """Create the event, or merge into the one that already means this.

    ``brand_ids`` maps brand id to its relation — subject, acquirer, partner.
    Returns the id and whether this call created it.
    """
    if event_type not in EVENT_TYPES:
        raise ValueError(f'unknown event type {event_type!r}')
    if occurred_at is None:
        precision = 'unknown'
    elif precision == 'unknown':
        precision = 'day'

    digest = fingerprint(event_type=event_type, brand_ids=brand_ids.keys(),
                         attributes=attributes, occurred_at=occurred_at,
                         precision=precision)

    row = conn.execute(text("""
        INSERT INTO bw_entity_events
            (event_type, event_subtype, title, description, occurred_at,
             date_precision, published_at, confidence, corroboration, status,
             attributes, extraction_version, dedupe_hash)
        VALUES (:type, :subtype, :title, :description, :occurred, :precision,
                :published, :confidence, 'uncorroborated', 'active',
                CAST(:attrs AS JSONB), :version, :hash)
        ON CONFLICT (dedupe_hash) DO UPDATE
           SET last_observed_at = NOW(), updated_at = NOW(),
               -- First-seen wins on the facts, but not against a better
               -- extractor. Refreshed only when the incoming version is newer:
               -- a re-run at the same version leaves the text untouched, so
               -- nothing churns, and a later *worse* pass cannot overwrite a
               -- good headline by being later.
               title = CASE
                   WHEN EXCLUDED.extraction_version IS NOT NULL
                    AND (bw_entity_events.extraction_version IS NULL
                         OR EXCLUDED.extraction_version
                            > bw_entity_events.extraction_version)
                   THEN EXCLUDED.title ELSE bw_entity_events.title END,
               description = CASE
                   WHEN EXCLUDED.extraction_version IS NOT NULL
                    AND (bw_entity_events.extraction_version IS NULL
                         OR EXCLUDED.extraction_version
                            > bw_entity_events.extraction_version)
                   THEN EXCLUDED.description
                   ELSE bw_entity_events.description END,
               extraction_version = GREATEST(
                   bw_entity_events.extraction_version,
                   EXCLUDED.extraction_version)
        RETURNING id, (xmax = 0) AS created
    """), {'type': event_type, 'subtype': subtype, 'title': title[:500],
           'description': description, 'occurred': occurred_at,
           'precision': precision, 'published': published_at,
           'confidence': confidence,
           'attrs': json.dumps(attributes or {}, default=str),
           'version': EXTRACTION_VERSION, 'hash': digest}).mappings().first()

    event_id = int(row['id'])
    if row['created']:
        for brand_id, relation in brand_ids.items():
            conn.execute(text("""
                INSERT INTO bw_entity_event_entities
                    (event_id, brand_id, relation)
                VALUES (:e, :b, :rel)
                ON CONFLICT (event_id, brand_id, relation) DO NOTHING
            """), {'e': event_id, 'b': int(brand_id), 'rel': relation})
    return {'event_id': event_id, 'created': bool(row['created']),
            'dedupe_hash': digest}


def add_evidence(conn, event_id: int, *, evidence_type: str,
                 independence_key: str, relationship: str = 'supports',
                 article_uri: Optional[str] = None,
                 snapshot_id: Optional[int] = None,
                 observation_id: Optional[int] = None,
                 mention_id: Optional[int] = None,
                 excerpt: Optional[str] = None) -> Optional[int]:
    """Attach one piece of evidence. Re-adding the same piece changes nothing."""
    row = conn.execute(text("""
        INSERT INTO bw_entity_event_evidence
            (event_id, evidence_type, article_uri, snapshot_id,
             observation_id, mention_id, relationship, independence_key,
             excerpt)
        VALUES (:e, :t, :uri, :snap, :obs, :men, :rel, :key, :ex)
        ON CONFLICT DO NOTHING
        RETURNING id
    """), {'e': event_id, 't': evidence_type, 'uri': article_uri,
           'snap': snapshot_id, 'obs': observation_id, 'men': mention_id,
           'rel': relationship, 'key': independence_key,
           'ex': (excerpt or '')[:1000] or None}).fetchone()
    return int(row[0]) if row else None


def recompute_corroboration(conn, event_id: int) -> Dict[str, Any]:
    """Set corroboration from the number of *distinct* supporting sources.

    Counting evidence rows instead would let one press release syndicated ten
    times look independently confirmed.
    """
    rows = conn.execute(text("""
        SELECT relationship, independence_key, evidence_type
          FROM bw_entity_event_evidence WHERE event_id = :e
    """), {'e': event_id}).mappings().all()

    supporting = {r['independence_key'] for r in rows
                  if r['relationship'] in ('supports', 'originates')}
    contradicting = {r['independence_key'] for r in rows
                     if r['relationship'] == 'contradicts'}
    owned = {k for k in supporting if k.startswith('owned:')}
    independent = supporting - owned
    # A company's own press page is not a primary document. Only a filing or
    # equivalent record is, and its key says so explicitly.
    has_primary = any(k.startswith(PRIMARY_DOCUMENT_PREFIXES)
                      for k in supporting)

    if has_primary:
        level = 'primary_document'
    elif len(independent) >= 2:
        level = 'corroborated'
    elif len(independent) == 1:
        level = 'single_source'
    elif owned:
        level = 'vendor_claim'
    else:
        level = 'uncorroborated'

    # A contradicted event stays visible. Hiding it would look identical to it
    # never having been found.
    status = 'pending_review' if contradicting else 'active'

    conn.execute(text("""
        UPDATE bw_entity_events
           SET corroboration = :level,
               -- A rejected or superseded event keeps that status. Setting it
               -- back to active here would resurrect a tombstone every time
               -- corroboration was recomputed.
               status = CASE WHEN status IN ('rejected', 'superseded')
                             THEN status ELSE :status END,
               updated_at = NOW()
         WHERE id = :e
    """), {'level': level, 'status': status, 'e': event_id})
    return {'corroboration': level, 'status': status,
            'independent_sources': len(independent),
            'owned_sources': len(owned),
            'contradicting_sources': len(contradicting)}


def record(conn, *, event_type: str, title: str, description: str,
           brand_ids: Dict[int, str], evidence: List[Dict[str, Any]],
           attributes: Optional[Dict[str, Any]] = None,
           occurred_at: Optional[datetime] = None,
           precision: str = 'day',
           published_at: Optional[datetime] = None,
           subtype: Optional[str] = None) -> Dict[str, Any]:
    """The whole cycle: upsert, attach evidence, recompute belief, project."""
    result = upsert_event(
        conn, event_type=event_type, title=title, description=description,
        brand_ids=brand_ids, attributes=attributes, occurred_at=occurred_at,
        precision=precision, published_at=published_at, subtype=subtype)

    for item in evidence:
        add_evidence(conn, result['event_id'], **item)

    result.update(recompute_corroboration(conn, result['event_id']))
    result['markets'] = project_to_markets(conn, result['event_id'])
    return result


# ---------------------------------------------------------------------------
# Market projection
# ---------------------------------------------------------------------------

def project_to_markets(conn, event_id: int) -> int:
    """Publish the event into every market that holds one of its subjects.

    The market row carries the market's own score, visibility and review
    status; the facts stay on the entity event. An undated event projects with
    a null date rather than one invented to satisfy a column.
    """
    event = conn.execute(text("""
        SELECT id, event_type, event_subtype, title, description, occurred_at,
               published_at, confidence, corroboration, status,
               extraction_version, dedupe_hash
          FROM bw_entity_events WHERE id = :e
    """), {'e': event_id}).mappings().first()
    if not event:
        return 0
    # A superseded event is a tombstone kept only to hold its fingerprint. Its
    # evidence now lives on the survivor, so projecting it would put the same
    # announcement on the market wire twice.
    if event['status'] in ('superseded', 'rejected'):
        conn.execute(text(
            'DELETE FROM bw_market_events WHERE entity_event_id = :e'),
            {'e': event_id})
        return 0

    markets = conn.execute(text("""
        SELECT DISTINCT mb.market_id
          FROM bw_entity_event_entities ee
          JOIN bw_market_brands mb ON mb.brand_id = ee.brand_id
         WHERE ee.event_id = :e AND mb.role <> 'excluded'
    """), {'e': event_id}).fetchall()

    projected = 0
    for (market_id,) in markets:
        row = conn.execute(text("""
            INSERT INTO bw_market_events
                (market_id, event_type, event_subtype, title, description,
                 event_date, published_at, confidence, corroboration, status,
                 extraction_version, content_hash, entity_event_id)
            VALUES (:m, :type, :subtype, :title, :description,
                    CAST(:occurred AS DATE), :published, :confidence,
                    :corroboration, :status, :version, :hash, :entity_event_id)
            ON CONFLICT (market_id, content_hash) DO UPDATE
               SET corroboration = EXCLUDED.corroboration,
                   status = EXCLUDED.status,
                   entity_event_id = EXCLUDED.entity_event_id,
                   updated_at = NOW()
            RETURNING id
        """), {'m': int(market_id), 'type': event['event_type'],
               'subtype': event['event_subtype'], 'title': event['title'],
               'description': event['description'],
               'occurred': event['occurred_at'],
               'published': event['published_at'],
               'confidence': event['confidence'],
               'corroboration': event['corroboration'],
               'status': event['status'],
               'version': event['extraction_version'],
               'hash': event['dedupe_hash'],
               'entity_event_id': event_id}).fetchone()
        if row:
            market_event_id = int(row[0])
            for (brand_id, relation) in conn.execute(text("""
                SELECT brand_id, relation FROM bw_entity_event_entities
                 WHERE event_id = :e
            """), {'e': event_id}).fetchall():
                conn.execute(text("""
                    INSERT INTO bw_event_vendors
                        (event_id, market_id, brand_id, relation)
                    VALUES (:e, :m, :b, :rel)
                    ON CONFLICT (event_id, brand_id, relation) DO NOTHING
                """), {'e': market_event_id, 'm': int(market_id),
                       'b': int(brand_id), 'rel': relation})
            projected += 1
    return projected


# ---------------------------------------------------------------------------
# Reads
# ---------------------------------------------------------------------------

def subject_key(reason: Optional[str]) -> Optional[str]:
    """What an event is *about*, from the reviewer's own words — or None.

    ``market_post_review`` already reads every vendor post once and writes a
    one-line reason. When that reason names something ("Partnership with Booz
    Allen Hamilton announced", "Launch of Org Brain product") it is a usable
    identity, and it cost nothing extra because the model has already run.

    When it does not name anything it is boilerplate, and using it would be
    destructive: Imperum's nine hiring posts all reduce to "Specific role being
    filled" or "Specific senior role being filled", so keying on the reason
    alone would collapse nine genuine job announcements into two. Requiring a
    proper noun is what separates the two cases — measured on this corpus, 113
    of 192 owned-post events get a key, and it merges 4 pairs and nothing else.

    Three alternatives were measured and rejected before this one. Text
    similarity ranks Imperum's *different* roles at 0.83 while the real Booz
    Allen duplicate scores 0.23, so it merges the wrong things. Bucketing the
    fingerprint by month collapses seven distinct System Two Security product
    posts into one. And the reviewer's reason without the proper-noun test is
    the nine-into-two case above.
    """
    if not reason:
        return None
    words = str(reason).split()
    named = any(re.match(r'^[A-Z][A-Za-z0-9&.\-]*$', w) for w in words[1:])
    # A lowercase dotted brand — "detections.ai", "exaforce.io" — names
    # something too, and never gets a capital.
    named = named or any('.' in w and w[:1].islower() for w in words)
    if not named:
        return None
    return re.sub(r'[^a-z0-9 ]', '', str(reason).lower()).strip() or None


def merge_duplicates(conn, *, announced_by: str = 'vendor') -> Dict[str, Any]:
    """Fold events that are the same announcement said twice.

    A vendor restating its own news creates a second event, because the
    fingerprint keys on the day and the two posts are days apart. Reconciling
    afterwards rather than changing the fingerprint is deliberate: changing
    identity would rehash every existing event and orphan the old rows, and
    this achieves the same result with no migration and no risk to events the
    rule does not apply to.

    Idempotent. The survivor is the lowest id — the first sighting, which is
    also the one whose date the timeline should keep.
    """
    rows = conn.execute(text("""
        SELECT e.id, e.event_type, ma.review_reason,
               (SELECT array_agg(DISTINCT ee.brand_id ORDER BY ee.brand_id)
                  FROM bw_entity_event_entities ee WHERE ee.event_id = e.id)
                   AS brands
          FROM bw_entity_events e
          JOIN bw_entity_event_evidence ev ON ev.event_id = e.id
          JOIN bw_market_articles ma ON ma.article_uri = ev.article_uri
         WHERE e.attributes->>'announced_by' = :who
           AND e.status NOT IN ('rejected', 'superseded')
         ORDER BY e.id
    """), {'who': announced_by}).mappings().all()

    groups: Dict[tuple, List[int]] = {}
    seen: set = set()
    for row in rows:
        if row['id'] in seen:
            continue
        seen.add(row['id'])
        key = subject_key(row['review_reason'])
        if not key or not row['brands']:
            continue
        groups.setdefault(
            (row['event_type'], tuple(row['brands']), key), []).append(row['id'])

    merged = 0
    for ids in groups.values():
        if len(ids) < 2:
            continue
        survivor, losers = ids[0], ids[1:]
        for loser in losers:
            # Evidence first, so the survivor inherits the second sighting and
            # its corroboration reflects both posts. ON CONFLICT because the
            # same article can already be attached to the survivor.
            conn.execute(text("""
                UPDATE bw_entity_event_evidence SET event_id = :s
                 WHERE event_id = :l
                   AND NOT EXISTS (
                       SELECT 1 FROM bw_entity_event_evidence x
                        WHERE x.event_id = :s
                          AND x.relationship = bw_entity_event_evidence.relationship
                          AND x.article_uri IS NOT DISTINCT FROM
                              bw_entity_event_evidence.article_uri
                          AND x.snapshot_id IS NOT DISTINCT FROM
                              bw_entity_event_evidence.snapshot_id
                          AND x.observation_id IS NOT DISTINCT FROM
                              bw_entity_event_evidence.observation_id
                          AND x.mention_id IS NOT DISTINCT FROM
                              bw_entity_event_evidence.mention_id)
            """), {'s': survivor, 'l': loser})
            conn.execute(text("""
                INSERT INTO bw_entity_event_entities (event_id, brand_id, relation)
                SELECT :s, brand_id, relation FROM bw_entity_event_entities
                 WHERE event_id = :l
                ON CONFLICT (event_id, brand_id, relation) DO NOTHING
            """), {'s': survivor, 'l': loser})
            # bw_market_events.entity_event_id carries no foreign key, so the
            # projection has to be cleared by hand or it points at a dead row.
            conn.execute(text("""
                DELETE FROM bw_market_events WHERE entity_event_id = :l
            """), {'l': loser})
            # Superseded, not deleted. Deleting frees the fingerprint, so the
            # next extractor pass recreates the duplicate and the merge folds
            # it again — stable in count but churning ids and repeating work
            # every run. A tombstone keeps the fingerprint claimed, so the
            # upsert updates this row instead of making a new one, and the
            # merge decision stays auditable.
            conn.execute(text("""
                UPDATE bw_entity_events
                   SET status = 'superseded',
                       attributes = attributes
                           || jsonb_build_object('superseded_by', :s),
                       updated_at = NOW()
                 WHERE id = :l
            """), {'l': loser, 's': survivor})
            merged += 1
        recompute_corroboration(conn, survivor)
        project_to_markets(conn, survivor)

    if merged:
        logger.info('merged %d duplicate event(s) into %d survivor(s)',
                    merged, sum(1 for v in groups.values() if len(v) > 1))
    return {'groups': sum(1 for v in groups.values() if len(v) > 1),
            'merged': merged}


def events_for_brand(conn, brand_id: int, limit: int = 50) -> List[Dict[str, Any]]:
    rows = conn.execute(text("""
        SELECT e.id, e.event_type, e.event_subtype, e.title, e.description,
               e.occurred_at, e.date_precision, e.corroboration, e.status,
               e.confidence, e.first_observed_at, e.last_observed_at,
               ee.relation,
               (SELECT count(DISTINCT independence_key)
                  FROM bw_entity_event_evidence v
                 WHERE v.event_id = e.id AND v.relationship IN
                       ('supports','originates')) AS sources
          FROM bw_entity_events e
          JOIN bw_entity_event_entities ee ON ee.event_id = e.id
         WHERE ee.brand_id = :b AND e.status NOT IN ('rejected', 'superseded')
         ORDER BY COALESCE(e.occurred_at, e.first_observed_at) DESC
         LIMIT :lim
    """), {'b': brand_id, 'lim': limit}).mappings().all()
    return [dict(r) for r in rows]


def evidence_for_event(conn, event_id: int) -> List[Dict[str, Any]]:
    rows = conn.execute(text("""
        SELECT v.evidence_type, v.relationship, v.independence_key,
               v.excerpt, v.article_uri, v.snapshot_id, v.observation_id,
               v.mention_id, a.title AS article_title, a.news_source, a.url
          FROM bw_entity_event_evidence v
          LEFT JOIN articles a ON a.uri = v.article_uri
         WHERE v.event_id = :e
         ORDER BY v.relationship, v.id
    """), {'e': event_id}).mappings().all()
    return [dict(r) for r in rows]
