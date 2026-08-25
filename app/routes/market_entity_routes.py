"""Entity reads and corrections, mounted under the Market Monitor router.

These endpoints live in their own module and are included from
``market_monitor_routes`` rather than being registered separately, so the
Market Monitor module gate keeps applying to them. A new router mounted on its
own would be reachable even with the module switched off.

Everything here answers the same question in different shapes: not just what a
value is, but where it came from and when. A vendor page that shows "310
people" without saying who counted them is the thing this whole change exists
to stop, so the field reads always carry the winning observation, its source,
its date and the policy that chose it.

Manual correction writes an observation like any other source and locks the
field. It does not edit the value in place, and it does not delete what the
providers said — locking means automatic resolution stops overriding a person,
while readings keep landing so the disagreement stays visible.

Every route requires a session, and every synchronous database call runs
through ``asyncio.to_thread``. One slow synchronous call on the event loop
takes the whole tenant down, which has happened here before.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import text

from app.database import get_database_instance
from app.security.session import verify_session
from app.services import (
    entity_events, entity_identity, entity_narratives, entity_observations,
    entity_projection, entity_resolution,
)
from app.services.entity_field_registry import (
    ENTITY_FIELD_POLICY_VERSION, REGISTRY, policy,
)

logger = logging.getLogger(__name__)

def require_entity_layer() -> None:
    """Make ENTITY_INTELLIGENCE_ENABLED a real switch for this surface.

    With the flag off these endpoints answer 404, which is what the Market
    Monitor API looked like before they existed. A rollback switch that leaves
    the new surface reachable is not a rollback, and it is worse than no switch
    because somebody will reach for it during an incident and believe it
    worked.
    """
    from app.services import entity_flags

    if not entity_flags.enabled():
        raise HTTPException(
            status_code=404,
            detail='entity intelligence is disabled '
                   '(ENTITY_INTELLIGENCE_ENABLED)')


router = APIRouter(tags=["Market Monitor"],
                   dependencies=[Depends(require_entity_layer)])

MAX_PAGE = 200


def _conn():
    return get_database_instance()._temp_get_connection()


def _actor(session) -> str:
    if isinstance(session, dict):
        return str(session.get('username') or session.get('email') or 'operator')
    return 'operator'


def _require_vendor(conn, market_id: int, brand_id: int) -> None:
    exists = conn.execute(text("""
        SELECT 1 FROM bw_market_brands
         WHERE market_id = :m AND brand_id = :b
    """), {'m': market_id, 'b': brand_id}).scalar()
    if not exists:
        raise HTTPException(status_code=404, detail='vendor not in this market')


# ---------------------------------------------------------------------------
# Fields and provenance
# ---------------------------------------------------------------------------

@router.get('/markets/{market_id}/vendors/{brand_id}/profile')
async def canonical_profile(market_id: int, brand_id: int,
                            session=Depends(verify_session)):
    """The current answer for each field, read from the canonical rows.

    Deriving this from a page of observations was wrong twice over: a settled
    or locked value eventually falls outside any recency window and vanishes
    from the page, and an observation's own status ('active') says nothing
    about whether the field is in conflict, stale, or held by an operator.
    Both come from the canonical row, so both are read from it.
    """
    def _work():
        conn = _conn()
        try:
            _require_vendor(conn, market_id, brand_id)
            fields = [dict(r) for r in conn.execute(text("""
                SELECT c.field_key, c.value_text, c.value_number, c.value_date,
                       c.unit, c.status, c.confidence, c.policy_version,
                       c.resolution_reason, c.resolved_at, c.stale_after,
                       c.locked, c.locked_by, c.lock_reason, c.observation_id,
                       o.source, o.observed_at, o.source_url
                  FROM bw_entity_canonical_fields c
                  JOIN bw_entity_observations o ON o.id = c.observation_id
                 WHERE c.brand_id = :b AND c.market_id IS NULL
                 ORDER BY c.field_key
            """), {'b': brand_id}).mappings().all()]

            membership = [dict(r) for r in conn.execute(text("""
                SELECT c.field_key, c.value_text, c.status, c.observation_id,
                       o.source, o.observed_at
                  FROM bw_entity_canonical_fields c
                  JOIN bw_entity_observations o ON o.id = c.observation_id
                 WHERE c.brand_id = :b AND c.market_id = :m
                 ORDER BY c.field_key
            """), {'b': brand_id, 'm': market_id}).mappings().all()]

            return {'fields': fields, 'market_fields': membership,
                    'conflicts': [f['field_key'] for f in fields
                                  if f['status'] == 'conflict'],
                    'stale_fields': [f['field_key'] for f in fields
                                     if f['status'] == 'stale'],
                    'locked_fields': [f['field_key'] for f in fields
                                      if f['locked']],
                    'policy_version': ENTITY_FIELD_POLICY_VERSION}
        finally:
            conn.close()
    return await asyncio.to_thread(_work)


@router.get('/markets/{market_id}/geography')
async def market_geography(market_id: int, session=Depends(verify_session)):
    """Where the market's vendors are, and what is disclosed about funding.

    Two measures that must not be conflated. **Concentration** is a headcount
    of companies per country and is complete: every vendor has a resolved
    country, so a count of five means five.

    **Funding is not complete and cannot be drawn as though it is.** Most
    vendors here never published an amount — India's five are all
    'Undisclosed', and 22 of the 53 US vendors are too. Summing what we have
    and plotting it per country would render those places as low-funded when
    the truth is that nobody said. So each country carries its own
    denominator: how many vendors the total covers, how many chose not to
    disclose, and how many we simply have no status for. A country with
    nothing disclosed returns ``total_musd: null``, never zero.

    Country granularity is all the data supports. ``hq_country`` is a country
    name; there is no city, so nothing here should be drawn at city precision.
    """
    def _work():
        conn = _conn()
        try:
            rows = [dict(r) for r in conn.execute(text("""
                SELECT p.hq_country AS country,
                       count(*) AS vendors,
                       count(p.funding_total_musd) AS vendors_with_amount,
                       count(*) FILTER (WHERE p.funding_status IN
                             ('Undisclosed', 'Bootstrapped')) AS not_disclosed,
                       count(*) FILTER (WHERE p.funding_status IS NULL)
                             AS status_unknown,
                       sum(p.funding_total_musd) AS total_musd,
                       max(p.funding_total_musd) AS largest_musd,
                       sum(p.employee_count) AS staff
                  FROM bw_entity_profiles p
                  JOIN bw_market_brands mb ON mb.brand_id = p.brand_id
                 WHERE mb.market_id = :m AND mb.role <> 'excluded'
                   AND p.hq_country IS NOT NULL
                 GROUP BY 1
                 ORDER BY 2 DESC, 1
            """), {'m': market_id}).mappings().all()]

            for row in rows:
                covered = int(row['vendors_with_amount'])
                # No disclosed amount anywhere in this country: the honest
                # answer is "unknown", and zero would read as "unfunded".
                row['total_musd'] = (float(row['total_musd'])
                                     if covered and row['total_musd'] is not None
                                     else None)
                row['largest_musd'] = (float(row['largest_musd'])
                                       if row['largest_musd'] is not None else None)
                row['funding_coverage'] = (covered / int(row['vendors'])
                                           if row['vendors'] else 0.0)
                row['staff'] = int(row['staff']) if row['staff'] else None

            placed = sum(int(r['vendors']) for r in rows)
            total = conn.execute(text("""
                SELECT count(*) FROM bw_market_brands
                 WHERE market_id = :m AND role <> 'excluded'
            """), {'m': market_id}).scalar()

            return {
                'countries': rows,
                'vendors_placed': placed,
                'vendors_total': int(total or 0),
                # Anyone whose country we never resolved is absent from the
                # map, and a map that quietly drops rows is a map that lies.
                'vendors_without_country': int(total or 0) - placed,
                'countries_with_no_disclosed_funding':
                    [r['country'] for r in rows if r['total_musd'] is None],
            }
        finally:
            conn.close()
    return await asyncio.to_thread(_work)


@router.get('/markets/{market_id}/vendors/{brand_id}/observations')
async def list_observations(market_id: int, brand_id: int,
                            field: Optional[str] = None,
                            source: Optional[str] = None,
                            limit: int = Query(50, le=MAX_PAGE),
                            cursor: Optional[int] = None,
                            session=Depends(verify_session)):
    """Every reading ever recorded, newest first, with its provenance."""
    def _work():
        conn = _conn()
        try:
            _require_vendor(conn, market_id, brand_id)
            where = ['o.brand_id = :b']
            params: Dict[str, Any] = {'b': brand_id, 'lim': limit + 1}
            if field:
                where.append('o.field_key = :field')
                params['field'] = field
            if source:
                where.append('o.source = :source')
                params['source'] = source
            if cursor:
                where.append('o.id < :cursor')
                params['cursor'] = cursor

            rows = [dict(r) for r in conn.execute(text(f"""
                SELECT o.id, o.field_key, o.value_json, o.value_text,
                       o.value_number, o.unit, o.source, o.source_url,
                       o.observed_at, o.effective_at, o.confidence,
                       o.authority, o.status, o.normalizer_version,
                       o.snapshot_id, o.article_uri, o.market_id,
                       (c.observation_id IS NOT NULL) AS is_canonical
                  FROM bw_entity_observations o
                  LEFT JOIN bw_entity_canonical_fields c
                         ON c.observation_id = o.id
                 WHERE {' AND '.join(where)}
                 ORDER BY o.id DESC
                 LIMIT :lim
            """), params).mappings().all()]

            has_more = len(rows) > limit
            rows = rows[:limit]
            return {'observations': rows,
                    'next_cursor': rows[-1]['id'] if has_more and rows else None,
                    'policy_version': ENTITY_FIELD_POLICY_VERSION}
        finally:
            conn.close()
    return await asyncio.to_thread(_work)


@router.get('/markets/{market_id}/vendors/{brand_id}/fields/{field_key}/history')
async def field_history(market_id: int, brand_id: int, field_key: str,
                        session=Depends(verify_session)):
    """One field's readings and every time the canonical answer moved.

    The series is split by source, because two sources measuring different
    things must not be drawn as one line.
    """
    try:
        field_policy = policy(field_key)
    except KeyError:
        raise HTTPException(status_code=404, detail=f'unknown field {field_key}')

    def _work():
        conn = _conn()
        try:
            _require_vendor(conn, market_id, brand_id)
            # Scope first: a market-relative field has one series per
            # membership, and an unscoped read showed a vendor that sits in
            # two markets both markets' category history in either one.
            scope_market = market_id if field_policy.scope == 'market' else None

            readings = [dict(r) for r in conn.execute(text("""
                SELECT id, source, value_text, value_number, unit, observed_at,
                       confidence, authority, status, metadata
                  FROM bw_entity_observations
                 WHERE brand_id = :b AND field_key = :f
                   AND market_id IS NOT DISTINCT FROM :m
                 ORDER BY observed_at, id
            """), {'b': brand_id, 'f': field_key,
                   'm': scope_market}).mappings().all()]

            series: Dict[str, List[Dict[str, Any]]] = {}
            for reading in readings:
                series.setdefault(field_policy.series_of(reading['source']),
                                  []).append(reading)

            transitions = [dict(r) for r in conn.execute(text("""
                SELECT old_observation_id, new_observation_id, old_status,
                       new_status, policy_version, reason, trigger, actor,
                       created_at
                  FROM bw_entity_resolution_log
                 WHERE brand_id = :b AND field_key = :f
                   AND market_id IS NOT DISTINCT FROM :m
                 ORDER BY created_at DESC LIMIT 50
            """), {'b': brand_id, 'f': field_key,
                   'm': scope_market}).mappings().all()]

            # Market-relative fields have one canonical row per membership,
            # so reading the global row returned nothing for taxonomy and made
            # the history panel look empty.
            current = conn.execute(text("""
                SELECT observation_id, value_text, value_number, unit, status,
                       confidence, policy_version, resolution_reason,
                       resolved_at, stale_after, locked, locked_by, lock_reason
                  FROM bw_entity_canonical_fields
                 WHERE brand_id = :b AND field_key = :f
                   AND market_id IS NOT DISTINCT FROM :m
            """), {'b': brand_id, 'f': field_key,
                   'm': scope_market}).mappings().first()

            return {'field_key': field_key,
                    'unit': field_policy.unit,
                    'strategy': field_policy.strategy,
                    'canonical': dict(current) if current else None,
                    # One line per compatible measurement, never merged.
                    'series_by_measurement': series,
                    'transitions': transitions}
        finally:
            conn.close()
    return await asyncio.to_thread(_work)


class FieldCorrection(BaseModel):
    value: Any
    reason: str = Field(..., min_length=3, max_length=500)
    lock: bool = True
    market_id: Optional[int] = None


@router.put('/markets/{market_id}/vendors/{brand_id}/fields/{field_key}')
async def correct_field(market_id: int, brand_id: int, field_key: str,
                        payload: FieldCorrection,
                        session=Depends(verify_session)):
    """Record an operator's value as an observation and lock the field.

    Nothing is overwritten. The correction is a ``manual`` observation that
    wins on authority, and the providers keep reporting whatever they report.
    """
    try:
        field_policy = policy(field_key)
    except KeyError:
        raise HTTPException(status_code=404, detail=f'unknown field {field_key}')

    # The market comes from the route. Accepting a different one in the body
    # let a request addressed to one market rewrite another market's taxonomy,
    # which no caller has any reason to do.
    if payload.market_id is not None and payload.market_id != market_id:
        raise HTTPException(
            status_code=400,
            detail=f'market_id in the body ({payload.market_id}) does not '
                   f'match the market in the path ({market_id})')

    if field_policy.scope == 'market':
        # Taxonomy belongs to a membership, so a correction without a market
        # is ambiguous rather than global.
        scope_market = market_id
    else:
        if payload.market_id is not None:
            raise HTTPException(
                status_code=400,
                detail=f'{field_key} is a company fact, not a market-relative '
                       f'one; drop market_id')
        scope_market = None

    actor = _actor(session)

    def _work():
        conn = _conn()
        try:
            _require_vendor(conn, market_id, brand_id)
            from datetime import datetime, timezone
            now = datetime.now(timezone.utc)
            observation_id = entity_observations.record_observation(
                conn, brand_id=brand_id, field_key=field_key,
                value=payload.value, source='manual',
                source_record_id=entity_observations.mint_source_record_id(
                    'manual', market_id=scope_market, field=field_key,
                    actor=actor, at=now.isoformat()),
                observed_at=now, market_id=scope_market, confidence=1.0,
                metadata={'reason': payload.reason, 'actor': actor,
                          'correction': True})
            if observation_id is None:
                raise HTTPException(
                    status_code=400,
                    detail=f'{payload.value!r} is not a usable value for '
                           f'{field_key}')

            result = entity_resolution.resolve_field(
                conn, brand_id, field_key, market_id=scope_market,
                trigger='manual', actor=actor)

            if payload.lock:
                conn.execute(text("""
                    UPDATE bw_entity_canonical_fields
                       SET locked = TRUE, locked_by = :actor,
                           lock_reason = :reason, status = 'manual_override',
                           updated_at = NOW()
                     WHERE brand_id = :b AND field_key = :f
                       AND market_id IS NOT DISTINCT FROM :m
                """), {'actor': actor, 'reason': payload.reason,
                       'b': brand_id, 'f': field_key, 'm': scope_market})

            if scope_market is None:
                entity_projection.project_entity(conn, brand_id)
            else:
                entity_projection.project_membership(conn, brand_id, scope_market)
            conn.commit()
            return {'observation_id': observation_id, 'locked': payload.lock,
                    'resolution': result}
        finally:
            conn.close()
    return await asyncio.to_thread(_work)


@router.post('/markets/{market_id}/vendors/{brand_id}/fields/{field_key}/unlock')
async def unlock_field(market_id: int, brand_id: int, field_key: str,
                       session=Depends(verify_session)):
    """Hand the field back to automatic resolution and recompute it."""
    actor = _actor(session)

    def _work():
        conn = _conn()
        try:
            _require_vendor(conn, market_id, brand_id)
            # Scope the unlock. Without the market clause, unlocking one
            # market's category released that field in every market the
            # company belongs to.
            scope_market = market_id if policy(field_key).scope == 'market' else None
            conn.execute(text("""
                UPDATE bw_entity_canonical_fields
                   SET locked = FALSE, locked_by = NULL, lock_reason = NULL,
                       updated_at = NOW()
                 WHERE brand_id = :b AND field_key = :f
                   AND market_id IS NOT DISTINCT FROM :m
            """), {'b': brand_id, 'f': field_key, 'm': scope_market})
            result = entity_resolution.resolve_field(
                conn, brand_id, field_key, market_id=scope_market,
                trigger='manual', actor=actor)
            entity_projection.project_entity(conn, brand_id)
            conn.commit()
            return {'unlocked': True, 'resolution': result}
        finally:
            conn.close()
    return await asyncio.to_thread(_work)


@router.post('/markets/{market_id}/vendors/{brand_id}/resolve')
async def replay_resolution(market_id: int, brand_id: int,
                            session=Depends(verify_session)):
    """Re-run the policy over existing observations. Collects nothing."""
    actor = _actor(session)

    def _work():
        conn = _conn()
        try:
            _require_vendor(conn, market_id, brand_id)
            results = entity_resolution.resolve_entity(
                conn, brand_id, trigger='policy_replay', actor=actor)
            results += entity_resolution.resolve_entity(
                conn, brand_id, market_id=market_id, trigger='policy_replay',
                actor=actor)
            entity_projection.project_entity(conn, brand_id)
            entity_projection.project_membership(conn, brand_id, market_id)
            conn.commit()
            return {'policy_version': ENTITY_FIELD_POLICY_VERSION,
                    'fields': results,
                    'changed': sum(1 for r in results if r['changed'])}
        finally:
            conn.close()
    return await asyncio.to_thread(_work)


# ---------------------------------------------------------------------------
# Events, mentions, identity, narratives
# ---------------------------------------------------------------------------

@router.get('/markets/{market_id}/vendors/{brand_id}/events')
async def vendor_events(market_id: int, brand_id: int,
                        limit: int = Query(50, le=MAX_PAGE),
                        session=Depends(verify_session)):
    def _work():
        conn = _conn()
        try:
            _require_vendor(conn, market_id, brand_id)
            events = entity_events.events_for_brand(conn, brand_id, limit=limit)
            for event in events:
                event['evidence'] = entity_events.evidence_for_event(
                    conn, event['id'])
            return {'events': events}
        finally:
            conn.close()
    return await asyncio.to_thread(_work)


@router.get('/markets/{market_id}/vendors/{brand_id}/mentions')
async def vendor_mentions(market_id: int, brand_id: int,
                          channel: Optional[str] = None,
                          platform: Optional[str] = None,
                          sentiment: Optional[str] = None,
                          limit: int = Query(50, le=MAX_PAGE),
                          cursor: Optional[int] = None,
                          session=Depends(verify_session)):
    """Mentions of this company, with owned content separated from external.

    The summary counts unevaluated mentions separately rather than folding
    them into neutral, so a sentiment figure never includes posts nobody
    judged.
    """
    def _work():
        conn = _conn()
        try:
            _require_vendor(conn, market_id, brand_id)
            where = ['m.brand_id = :b']
            params: Dict[str, Any] = {'b': brand_id, 'lim': limit + 1}
            if channel:
                where.append('m.channel = :channel')
                params['channel'] = channel
            if platform:
                where.append('m.platform = :platform')
                params['platform'] = platform
            if sentiment:
                where.append('m.sentiment ILIKE :sentiment')
                params['sentiment'] = sentiment
            if cursor:
                where.append('m.id < :cursor')
                params['cursor'] = cursor

            rows = [dict(r) for r in conn.execute(text(f"""
                SELECT m.id, m.article_uri, m.mention_type, m.channel,
                       m.platform, m.excerpt, m.relevance, m.sentiment,
                       m.stance, m.status, m.evaluated_at,
                       a.title, a.url, a.news_source, a.publication_date,
                       sa.handle AS author_handle, sa.platform_user_id,
                       si.relationship AS author_relationship,
                       si.status AS author_identity_status
                  FROM bw_entity_mentions m
                  JOIN articles a ON a.uri = m.article_uri
                  LEFT JOIN bw_entity_content_links l ON l.id = m.content_link_id
                  LEFT JOIN social_accounts sa ON sa.id = l.social_account_id
                  LEFT JOIN bw_entity_social_identities si
                         ON si.social_account_id = sa.id
                        AND si.brand_id = m.brand_id AND si.valid_to IS NULL
                 WHERE {' AND '.join(where)}
                 ORDER BY m.id DESC LIMIT :lim
            """), params).mappings().all()]

            has_more = len(rows) > limit
            rows = rows[:limit]

            summary = [dict(r) for r in conn.execute(text("""
                SELECT channel, platform,
                       count(*) AS total,
                       count(*) FILTER (WHERE status = 'pending') AS unevaluated,
                       count(*) FILTER (WHERE sentiment ILIKE 'positive') AS positive,
                       count(*) FILTER (WHERE sentiment ILIKE 'negative') AS negative,
                       count(*) FILTER (WHERE stance = 'owned_claim') AS owned_claims
                  FROM bw_entity_mentions WHERE brand_id = :b
                 GROUP BY 1, 2 ORDER BY 3 DESC
            """), {'b': brand_id}).mappings().all()]

            return {'mentions': rows, 'summary': summary,
                    'next_cursor': rows[-1]['id'] if has_more and rows else None}
        finally:
            conn.close()
    return await asyncio.to_thread(_work)


@router.get('/markets/{market_id}/vendors/{brand_id}/social-identities')
async def list_identities(market_id: int, brand_id: int,
                          session=Depends(verify_session)):
    def _work():
        conn = _conn()
        try:
            _require_vendor(conn, market_id, brand_id)
            return {'identities': entity_identity.identities_for(conn, brand_id)}
        finally:
            conn.close()
    return await asyncio.to_thread(_work)


class IdentityProposal(BaseModel):
    platform: str = Field(..., max_length=24)
    handle: str = Field(..., max_length=200)
    relationship: str = Field('owned_company', max_length=24)
    platform_user_id: Optional[str] = None
    note: Optional[str] = None


@router.post('/markets/{market_id}/vendors/{brand_id}/social-identities')
async def add_identity(market_id: int, brand_id: int, payload: IdentityProposal,
                       session=Depends(verify_session)):
    """An operator asserting a mapping. Manual is the only method that
    verifies an executive or a previously rejected account."""
    actor = _actor(session)

    def _work():
        conn = _conn()
        try:
            _require_vendor(conn, market_id, brand_id)
            account = entity_identity.upsert_account(
                conn, platform=payload.platform, handle=payload.handle,
                platform_user_id=payload.platform_user_id)
            outcome = entity_identity.propose_identity(
                conn, brand_id=brand_id,
                social_account_id=account['account_id'],
                relationship=payload.relationship,
                verification_method='manual', actor=actor,
                provenance={'note': payload.note, 'actor': actor})
            conn.commit()
            return {'account': account, 'identity': outcome}
        finally:
            conn.close()
    return await asyncio.to_thread(_work)


class IdentityDecision(BaseModel):
    action: str = Field(..., pattern='^(verify|reject)$')
    reason: Optional[str] = None


@router.put('/markets/{market_id}/vendors/{brand_id}/social-identities/{mapping_id}')
async def decide_identity(market_id: int, brand_id: int, mapping_id: int,
                          payload: IdentityDecision,
                          session=Depends(verify_session)):
    actor = _actor(session)

    def _work():
        conn = _conn()
        try:
            _require_vendor(conn, market_id, brand_id)
            # The mapping id came from the URL and nothing tied it to the
            # vendor in the path, so one vendor's page could verify or reject
            # another vendor's account mapping.
            owner = conn.execute(text("""
                SELECT brand_id FROM bw_entity_social_identities WHERE id = :i
            """), {'i': mapping_id}).scalar()
            if owner is None:
                raise HTTPException(status_code=404, detail='no such mapping')
            if int(owner) != brand_id:
                raise HTTPException(
                    status_code=404,
                    detail='that mapping belongs to a different vendor')
            if payload.action == 'verify':
                entity_identity.verify_identity(conn, mapping_id, actor=actor)
            else:
                entity_identity.reject_identity(conn, mapping_id, actor=actor,
                                                reason=payload.reason or '')
            conn.commit()
            return {'mapping_id': mapping_id, 'action': payload.action}
        finally:
            conn.close()
    return await asyncio.to_thread(_work)


@router.get('/markets/{market_id}/vendors/{brand_id}/narratives')
async def list_narratives(market_id: int, brand_id: int,
                          session=Depends(verify_session)):
    def _work():
        conn = _conn()
        try:
            _require_vendor(conn, market_id, brand_id)
            return {'narratives': entity_narratives.narratives_for(conn, brand_id)}
        finally:
            conn.close()
    return await asyncio.to_thread(_work)


class NarrativeRequest(BaseModel):
    narrative_type: str = Field('brand_brief', max_length=24)
    days: int = Field(90, ge=1, le=730)
    facts_only: bool = True


@router.post('/markets/{market_id}/vendors/{brand_id}/narratives')
async def build_narrative(market_id: int, brand_id: int,
                          payload: NarrativeRequest,
                          session=Depends(verify_session)):
    """Assemble the facts pack, and only then generate.

    ``facts_only`` returns the pack without calling a model, which is what the
    UI uses to show an operator what a brief would be written from before
    anything is spent generating one.
    """
    def _work():
        conn = _conn()
        try:
            _require_vendor(conn, market_id, brand_id)
            facts = entity_narratives.build_facts(conn, brand_id,
                                                  days=payload.days)
            return {'facts': facts,
                    'evidence_available':
                        len(entity_narratives.evidence_from_facts(facts)),
                    'generated': False}
        finally:
            conn.close()

    if not payload.facts_only:
        raise HTTPException(
            status_code=501,
            detail='model-backed generation is not enabled; request '
                   'facts_only to see what a brief would be written from')
    return await asyncio.to_thread(_work)


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

@router.get('/markets/{market_id}/entity-health')
async def entity_health(market_id: int, session=Depends(verify_session)):
    """What is stale, disputed, or waiting — so "nothing changed" is
    distinguishable from "nothing ran"."""
    def _work():
        conn = _conn()
        try:
            counts = conn.execute(text("""
                SELECT
                  (SELECT count(*) FROM bw_entity_canonical_fields c
                     JOIN bw_market_brands mb ON mb.brand_id = c.brand_id
                    WHERE mb.market_id = :m AND c.status = 'stale') AS stale_fields,
                  (SELECT count(*) FROM bw_entity_canonical_fields c
                     JOIN bw_market_brands mb ON mb.brand_id = c.brand_id
                    WHERE mb.market_id = :m AND c.status = 'conflict') AS conflicts,
                  (SELECT count(*) FROM bw_entity_canonical_fields c
                     JOIN bw_market_brands mb ON mb.brand_id = c.brand_id
                    WHERE mb.market_id = :m AND c.locked) AS locked_fields,
                  (SELECT count(*) FROM bw_vendor_snapshots
                    WHERE normalization_status = 'pending') AS pending_normalization,
                  (SELECT count(*) FROM bw_vendor_snapshots
                    WHERE normalization_status = 'failed') AS failed_normalization,
                  (SELECT count(*) FROM bw_entity_mentions m
                     JOIN bw_market_brands mb ON mb.brand_id = m.brand_id
                    WHERE mb.market_id = :m AND m.status = 'pending')
                      AS pending_mention_evaluation,
                  (SELECT count(*) FROM bw_review_tasks
                    WHERE status = 'open' AND kind = 'identity_conflict')
                      AS identity_conflicts,
                  (SELECT count(*) FROM bw_review_tasks
                    WHERE status = 'open' AND market_id IS NULL)
                      AS entity_global_tasks,
                  (SELECT count(*) FROM bw_entity_events) AS events,
                  (SELECT count(*) FROM bw_entity_events
                    WHERE corroboration = 'vendor_claim') AS vendor_claims
            """), {'m': market_id}).mappings().first()

            oldest = conn.execute(text("""
                SELECT min(created_at) FROM bw_entity_mentions
                 WHERE status = 'pending'
            """)).scalar()

            return {'market_id': market_id, **dict(counts),
                    'oldest_pending_mention': oldest,
                    'policy_version': ENTITY_FIELD_POLICY_VERSION,
                    'known_fields': sorted(REGISTRY)}
        finally:
            conn.close()
    return await asyncio.to_thread(_work)
