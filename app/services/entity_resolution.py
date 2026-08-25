"""Choosing which observation is currently true, and saying why.

Resolution is a pointer move, not an overwrite. Every reading a source has ever
given us stays in ``bw_entity_observations``; the canonical row records which
one wins today, which policy version chose it, and in one sentence why. Run the
same observations through the same policy version twice and the same answer
comes out, which is what makes a replay after a policy change explainable
rather than mysterious.

The ordering is not a global list of good sources. It is, in order: is this
observation eligible for this field at all, has an operator locked the field,
then confidence, authority, effective time, and finally the observation id so
that two identical candidates still resolve the same way every time.

Three refusals are worth naming, because each one is a way a system like this
usually goes wrong.

**A missing value never wins.** Nulls are filtered before ranking, so a
provider that stopped returning a field cannot erase what we already knew.

**A total that went down is not news until somebody says it is.** Funding
accumulates, so a smaller total is a correction or a mistake. The resolver
keeps the larger figure, marks the field in conflict, and files a task.

**A collapse in headcount is held, not published.** A drop past the policy's
threshold needs a second source before it moves the canonical value, because
the far more common cause is a provider changing what it counts.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import text

from app.services import entity_review
from app.services.entity_field_registry import (
    ENTITY_FIELD_POLICY_VERSION, MARKET_FIELDS, SCOPE_MARKET, ENTITY_FIELDS,
    FieldPolicy, policy,
)

logger = logging.getLogger(__name__)

# How close in authority a rival has to be before its disagreement counts as a
# conflict rather than a weaker source being outranked as designed.
PEER_AUTHORITY_BAND = 15


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _effective(row: Dict[str, Any]) -> datetime:
    value = row.get('effective_at') or row.get('observed_at')
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    return _now()


def _value(row: Dict[str, Any]) -> Any:
    raw = row.get('value_json')
    if isinstance(raw, str):
        try:
            return json.loads(raw)
        except ValueError:
            return raw
    return raw


def _eligible(row: Dict[str, Any], p: FieldPolicy) -> bool:
    """Whether this observation may answer this field at all."""
    source = row['source']
    if not p.accepts(source):
        return False
    if source in p.verified_only:
        meta = row.get('metadata') or {}
        if isinstance(meta, str):
            try:
                meta = json.loads(meta)
            except ValueError:
                meta = {}
        # PitchBook and ZoomInfo mappings have never been checked against a
        # live response. Until one is, their readings are stored but not used.
        if not meta.get('verified'):
            return False
    return True


def _rank_key(row: Dict[str, Any]):
    return (row.get('confidence') if row.get('confidence') is not None else 0.5,
            int(row['authority']),
            _effective(row),
            int(row['id']))


def _consensus_winner(candidates: List[Dict[str, Any]]) -> Dict[str, Any]:
    """For fields that should stop moving once settled, e.g. founded year.

    Weight each distinct value by the authority of the distinct sources that
    assert it, so three weak sources agreeing beat one strong outlier, and a
    year does not flip back and forth as collection runs land.
    """
    groups: Dict[str, Dict[str, Any]] = {}
    for row in candidates:
        key = str(_value(row))
        group = groups.setdefault(key, {'rows': [], 'sources': {}})
        group['rows'].append(row)
        # One source votes once, at its highest authority for that value.
        group['sources'][row['source']] = max(
            group['sources'].get(row['source'], 0), int(row['authority']))
    best = max(groups.values(),
               key=lambda g: (sum(g['sources'].values()),
                              max(g['sources'].values()),
                              max(_effective(r) for r in g['rows'])))
    return max(best['rows'], key=_rank_key)


def _load_candidates(conn, brand_id: int, field_key: str,
                     market_id: Optional[int]) -> List[Dict[str, Any]]:
    rows = conn.execute(text("""
        SELECT id, brand_id, market_id, field_key, value_json, value_text,
               value_number, value_date, unit, source, source_record_id,
               observed_at, effective_at, expires_at, confidence, authority,
               metadata
          FROM bw_entity_observations
         WHERE brand_id = :brand_id
           AND field_key = :field_key
           AND market_id IS NOT DISTINCT FROM :market_id
           AND status = 'active'
           AND (expires_at IS NULL OR expires_at > NOW())
         ORDER BY id
    """), {'brand_id': brand_id, 'field_key': field_key,
           'market_id': market_id}).mappings().all()
    return [dict(r) for r in rows]


def _current_canonical(conn, brand_id: int, field_key: str,
                       market_id: Optional[int]) -> Optional[Dict[str, Any]]:
    row = conn.execute(text("""
        SELECT id, observation_id, value_json, value_number, status, locked,
               policy_version
          FROM bw_entity_canonical_fields
         WHERE brand_id = :brand_id AND field_key = :field_key
           AND market_id IS NOT DISTINCT FROM :market_id
    """), {'brand_id': brand_id, 'field_key': field_key,
           'market_id': market_id}).mappings().first()
    return dict(row) if row else None


def resolve_field(conn, brand_id: int, field_key: str, *,
                  market_id: Optional[int] = None,
                  trigger: str = 'ingest',
                  actor: Optional[str] = None) -> Dict[str, Any]:
    """Resolve one field for one entity. Returns what happened and why."""
    p = policy(field_key)
    if (p.scope == SCOPE_MARKET) != (market_id is not None):
        raise ValueError(
            f"{field_key!r} is {p.scope}-scoped; market_id={market_id!r}")

    outcome = {'brand_id': brand_id, 'market_id': market_id,
               'field_key': field_key, 'changed': False,
               'status': None, 'observation_id': None, 'reason': ''}

    candidates = [r for r in _load_candidates(conn, brand_id, field_key, market_id)
                  if _eligible(r, p)]
    current = _current_canonical(conn, brand_id, field_key, market_id)

    if not candidates:
        outcome['reason'] = 'no eligible observations'
        return outcome

    if p.strategy == 'stable_consensus':
        winner = _consensus_winner(candidates)
        reason = 'highest-authority consensus value'
    else:
        winner = max(candidates, key=_rank_key)
        reason = f"highest authority ({winner['source']}), most recent reading"

    status = 'current'
    review_target: Optional[Dict[str, Any]] = None

    # Freshness. A stale winner still wins — dropping it would replace a known
    # old value with nothing — but the field says so.
    if p.stale_after_seconds is not None:
        age = _now() - _effective(winner)
        if age > timedelta(seconds=p.stale_after_seconds):
            status = 'stale'
            reason += f"; last read {age.days}d ago"

    # Disagreement among peers of the winner.
    rival = _find_rival(candidates, winner, p)
    if rival is not None:
        status = 'conflict'
        reason += f"; disagrees with {rival['source']}"
        review_target = rival

    # Guards against a worse value replacing a better one.
    held = _hold_against_regression(conn, p, current, winner, brand_id,
                                    field_key, candidates)
    if held is not None:
        outcome.update(held)
        outcome['status'] = 'conflict'
        return outcome

    if current and current['locked']:
        # The operator's value stands. Incoming readings are still stored and
        # still counted as conflicts, so the lock is visible rather than silent.
        locked_status = 'conflict' if rival is not None or _value(winner) != _json(
            current['value_json']) else 'manual_override'
        changed = _write_canonical(
            conn, brand_id, field_key, market_id,
            observation_id=current['observation_id'], status=locked_status,
            reason='locked by operator; automatic resolution suppressed',
            policy=p, trigger=trigger, actor=actor, current=current,
            winner=None)
        outcome.update(changed=changed, status=locked_status,
                       observation_id=current['observation_id'],
                       reason='locked by operator')
        return outcome

    changed = _write_canonical(
        conn, brand_id, field_key, market_id,
        observation_id=int(winner['id']), status=status, reason=reason,
        policy=p, trigger=trigger, actor=actor, current=current, winner=winner)

    if status == 'conflict' and review_target is not None:
        entity_review.field_conflict(
            conn, brand_id=brand_id, field_key=field_key, market_id=market_id,
            winner={'id': winner['id'], 'source': winner['source'],
                    'value': _value(winner), 'observed_at': winner['observed_at']},
            rival={'id': review_target['id'], 'source': review_target['source'],
                   'value': _value(review_target),
                   'observed_at': review_target['observed_at']})
    elif status in ('current', 'stale'):
        entity_review.auto_close(conn, kind=entity_review.KIND_FIELD_CONFLICT,
                                 brand_id=brand_id, field=field_key,
                                 market_id=market_id)

    outcome.update(changed=changed, status=status,
                   observation_id=int(winner['id']), reason=reason)
    return outcome


def _json(raw: Any) -> Any:
    if isinstance(raw, str):
        try:
            return json.loads(raw)
        except ValueError:
            return raw
    return raw


def _find_rival(candidates: List[Dict[str, Any]], winner: Dict[str, Any],
                p: FieldPolicy) -> Optional[Dict[str, Any]]:
    """The strongest fresh candidate that materially disagrees, if any."""
    if p.conflict.kind == 'none':
        return None
    floor = int(winner['authority']) - PEER_AUTHORITY_BAND
    cutoff = (_now() - timedelta(seconds=p.stale_after_seconds)
              if p.stale_after_seconds else None)
    rivals = []
    for row in candidates:
        if row['id'] == winner['id'] or int(row['authority']) < floor:
            continue
        if cutoff is not None and _effective(row) < cutoff:
            continue
        # Sources measuring different things are not in disagreement.
        if p.series_of(row['source']) != p.series_of(winner['source']):
            continue
        if p.conflict.disagrees(_value(winner), _value(row)):
            rivals.append(row)
    return max(rivals, key=_rank_key) if rivals else None


def _hold_against_regression(conn, p: FieldPolicy,
                             current: Optional[Dict[str, Any]],
                             winner: Dict[str, Any], brand_id: int,
                             field_key: str,
                             candidates: List[Dict[str, Any]],
                             ) -> Optional[Dict[str, Any]]:
    """Refuse a move that is more likely an error than a change.

    Returns a partial outcome when the previous value is held, or None when
    the winner may proceed.
    """
    if current is None:
        return None
    old = _json(current['value_json'])
    new = _value(winner)
    try:
        old_n, new_n = float(old), float(new)
    except (TypeError, ValueError):
        return None
    if new_n >= old_n:
        return None

    meta = winner.get('metadata') or {}
    if isinstance(meta, str):
        try:
            meta = json.loads(meta)
        except ValueError:
            meta = {}
    if meta.get('correction'):
        return None

    if not p.allow_decrease:
        entity_review.field_decrease(
            conn, brand_id=brand_id, field_key=field_key, old_value=old,
            new_value=new, source=winner['source'],
            observation_id=int(winner['id']), severity='high')
        return {'changed': False, 'observation_id': current['observation_id'],
                'reason': f'held {old!r}: totals do not fall without a '
                          f'stated correction'}

    if p.decrease_review_ratio and new_n < old_n * (1 - p.decrease_review_ratio):
        corroborated = any(
            r['id'] != winner['id']
            and r['source'] != winner['source']
            and not p.conflict.disagrees(new, _value(r))
            for r in candidates)
        if not corroborated:
            entity_review.field_decrease(
                conn, brand_id=brand_id, field_key=field_key, old_value=old,
                new_value=new, source=winner['source'],
                observation_id=int(winner['id']))
            return {'changed': False,
                    'observation_id': current['observation_id'],
                    'reason': f'held {old!r}: {winner["source"]} reports a '
                              f'drop past the review threshold, uncorroborated'}
    return None


def _write_canonical(conn, brand_id: int, field_key: str,
                     market_id: Optional[int], *, observation_id: int,
                     status: str, reason: str, policy: FieldPolicy,
                     trigger: str, actor: Optional[str],
                     current: Optional[Dict[str, Any]],
                     winner: Optional[Dict[str, Any]]) -> bool:
    """Upsert the canonical row; log only when something actually moved."""
    moved = (current is None
             or int(current['observation_id']) != int(observation_id)
             or current['status'] != status
             or current['policy_version'] != ENTITY_FIELD_POLICY_VERSION)

    stale_after = None
    if winner is not None and policy.stale_after_seconds is not None:
        stale_after = _effective(winner) + timedelta(
            seconds=policy.stale_after_seconds)

    if current is not None and current['locked']:
        # A locked row keeps its observation. Only the status and the sentence
        # explaining it move, so the operator can see that automatic
        # resolution disagrees without it changing anything underneath them.
        conn.execute(text("""
            UPDATE bw_entity_canonical_fields
               SET status = :status, resolution_reason = :reason,
                   policy_version = :policy_version, resolved_at = NOW(),
                   updated_at = NOW()
             WHERE id = :id
        """), {'status': status, 'reason': reason, 'id': current['id'],
               'policy_version': ENTITY_FIELD_POLICY_VERSION})
    else:
        conn.execute(text(_UPSERT_SQL[market_id is None]), {
            'status': status, 'policy_version': ENTITY_FIELD_POLICY_VERSION,
            'reason': reason, 'stale_after': stale_after,
            'observation_id': observation_id})

    if moved:
        conn.execute(text("""
            INSERT INTO bw_entity_resolution_log
                (brand_id, market_id, field_key, old_observation_id,
                 new_observation_id, old_status, new_status, policy_version,
                 reason, trigger, actor)
            VALUES
                (:brand_id, :market_id, :field_key, :old_obs, :new_obs,
                 :old_status, :new_status, :policy_version, :reason, :trigger,
                 :actor)
        """), {
            'brand_id': brand_id, 'market_id': market_id,
            'field_key': field_key,
            'old_obs': current['observation_id'] if current else None,
            'new_obs': observation_id,
            'old_status': current['status'] if current else None,
            'new_status': status,
            'policy_version': ENTITY_FIELD_POLICY_VERSION, 'reason': reason,
            'trigger': trigger, 'actor': actor})
    return moved


def _build_upsert(global_scope: bool) -> str:
    """One statement per scope, because the two partial indexes differ.

    The row is built from the winning observation itself rather than from
    values passed in, so the canonical copy cannot drift from the observation
    it points at.
    """
    target = ("(brand_id, field_key) WHERE market_id IS NULL" if global_scope
              else "(market_id, brand_id, field_key) WHERE market_id IS NOT NULL")
    return f"""
        INSERT INTO bw_entity_canonical_fields
            (brand_id, market_id, field_key, observation_id, value_json,
             value_text, value_number, value_date, unit, status, confidence,
             policy_version, resolution_reason, resolved_at, stale_after,
             updated_at)
        SELECT o.brand_id, o.market_id, o.field_key, o.id, o.value_json,
               o.value_text, o.value_number, o.value_date, o.unit, :status,
               o.confidence, :policy_version, :reason, NOW(), :stale_after,
               NOW()
          FROM bw_entity_observations o
         WHERE o.id = :observation_id
        ON CONFLICT {target} DO UPDATE SET
            observation_id = EXCLUDED.observation_id,
            value_json = EXCLUDED.value_json,
            value_text = EXCLUDED.value_text,
            value_number = EXCLUDED.value_number,
            value_date = EXCLUDED.value_date,
            unit = EXCLUDED.unit,
            status = EXCLUDED.status,
            confidence = EXCLUDED.confidence,
            policy_version = EXCLUDED.policy_version,
            resolution_reason = EXCLUDED.resolution_reason,
            resolved_at = EXCLUDED.resolved_at,
            stale_after = EXCLUDED.stale_after,
            updated_at = NOW()
    """


# Keyed by "is this the global scope", built once at import.
_UPSERT_SQL = {True: _build_upsert(True), False: _build_upsert(False)}


def resolve_entity(conn, brand_id: int, *, market_id: Optional[int] = None,
                   fields: Optional[List[str]] = None,
                   trigger: str = 'ingest',
                   actor: Optional[str] = None) -> List[Dict[str, Any]]:
    """Resolve every field in scope for one entity.

    Global fields are resolved once per entity. Market fields are resolved per
    membership, which is why ``market_id`` selects the scope rather than
    filtering it.
    """
    if fields is None:
        fields = sorted(MARKET_FIELDS if market_id is not None else ENTITY_FIELDS)
    results = []
    for field_key in fields:
        try:
            results.append(resolve_field(conn, brand_id, field_key,
                                         market_id=market_id, trigger=trigger,
                                         actor=actor))
        except Exception:                          # noqa: BLE001
            logger.exception("resolve failed brand_id=%s field=%s market_id=%s "
                             "policy_version=%s", brand_id, field_key,
                             market_id, ENTITY_FIELD_POLICY_VERSION)
    return results
