"""Review tasks for things the resolver refuses to decide on its own.

Two sources disagreeing about a headcount, a funding total that went down, an
account that two companies both claim to own — none of these should be settled
by picking the newest row and moving on. They become tasks.

Tasks come in two shapes and the difference matters more than it looks.
A membership problem belongs to one market. A field conflict or an identity
dispute belongs to the entity, and filing it against whichever market happened
to trigger collection would hide it from every other market the company is in.
So ``market_id`` is nullable, and dedup runs through two partial indexes rather
than one.

That split is not tidiness. PostgreSQL treats null indexed values as distinct,
so a single index containing a nullable ``market_id`` deduplicates nothing for
the rows that have no market: the same conflict would file a fresh task on
every resolver pass until somebody noticed the queue filling up.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, Optional

from sqlalchemy import text

logger = logging.getLogger(__name__)

SEVERITIES = ('low', 'medium', 'high')

# Kinds this module files. Existing importer kinds are left alone.
KIND_FIELD_CONFLICT = 'field_conflict'
KIND_FIELD_DECREASE = 'field_decrease'
KIND_IDENTITY_CONFLICT = 'identity_conflict'
KIND_STALE_SOURCE = 'stale_source'


def open_task(conn, *, kind: str, message: str,
              brand_id: Optional[int] = None,
              market_id: Optional[int] = None,
              field: Optional[str] = None,
              severity: str = 'medium',
              source_ref: Optional[Dict[str, Any]] = None) -> Optional[int]:
    """File a task, or do nothing if the identical one is already open.

    Returns the task id when one was created, None when it already existed.
    The two conflict targets mirror the two partial unique indexes; using the
    wrong one for a null market silently inserts a duplicate.
    """
    if severity not in SEVERITIES:
        raise ValueError(f"unknown severity {severity!r}")

    params = {
        'market_id': market_id, 'brand_id': brand_id, 'kind': kind,
        'severity': severity, 'field': field, 'message': message,
        'source_ref': json.dumps(source_ref or {}),
    }
    conflict = ("(market_id, kind, COALESCE(brand_id, 0), COALESCE(field, ''), "
                "md5(message)) WHERE market_id IS NOT NULL"
                if market_id is not None else
                "(kind, COALESCE(brand_id, 0), COALESCE(field, ''), "
                "md5(message)) WHERE market_id IS NULL")

    row = conn.execute(text(f"""
        INSERT INTO bw_review_tasks
            (market_id, brand_id, kind, severity, status, field, message,
             source_ref, target_field)
        VALUES
            (:market_id, :brand_id, :kind, :severity, 'open', :field,
             :message, CAST(:source_ref AS JSONB), :field)
        ON CONFLICT {conflict} DO NOTHING
        RETURNING id
    """), params).fetchone()
    return int(row[0]) if row else None


def auto_close(conn, *, kind: str, brand_id: Optional[int],
               field: Optional[str], market_id: Optional[int] = None,
               outcome: str = 'superseded') -> int:
    """Close open tasks that later data has answered.

    Used when a conflict resolves itself — a third source arrives and agrees,
    or a decrease is corroborated. Closing is recorded as ``auto_closed_at`` so
    a queue that emptied on its own is distinguishable from one a person
    worked through.
    """
    result = conn.execute(text("""
        UPDATE bw_review_tasks
           SET status = 'resolved', outcome = :outcome,
               auto_closed_at = NOW(), resolved_at = NOW(), updated_at = NOW()
         WHERE status = 'open' AND kind = :kind
           AND brand_id IS NOT DISTINCT FROM :brand_id
           AND COALESCE(field, '') = COALESCE(:field, '')
           AND market_id IS NOT DISTINCT FROM :market_id
    """), {'kind': kind, 'brand_id': brand_id, 'field': field,
           'market_id': market_id, 'outcome': outcome})
    return int(result.rowcount or 0)


def field_conflict(conn, *, brand_id: int, field_key: str,
                   winner: Dict[str, Any], rival: Dict[str, Any],
                   market_id: Optional[int] = None) -> Optional[int]:
    """File a disagreement between two credible, fresh readings."""
    message = (
        f"{field_key}: {winner['source']} says {winner['value']!r} "
        f"({_when(winner)}), {rival['source']} says {rival['value']!r} "
        f"({_when(rival)}). Kept the higher-authority reading and marked the "
        f"field in conflict."
    )
    return open_task(
        conn, kind=KIND_FIELD_CONFLICT, message=message, brand_id=brand_id,
        market_id=market_id, field=field_key, severity='medium',
        source_ref={'winner_observation_id': winner.get('id'),
                    'rival_observation_id': rival.get('id')})


def field_decrease(conn, *, brand_id: int, field_key: str,
                   old_value: Any, new_value: Any, source: str,
                   observation_id: Optional[int] = None,
                   severity: str = 'medium') -> Optional[int]:
    """File a drop large enough that it is more likely an error than news."""
    message = (
        f"{field_key} fell from {old_value!r} to {new_value!r} according to "
        f"{source}. Held the previous value pending corroboration."
    )
    return open_task(
        conn, kind=KIND_FIELD_DECREASE, message=message, brand_id=brand_id,
        field=field_key, severity=severity,
        source_ref={'observation_id': observation_id,
                    'old_value': old_value, 'new_value': new_value})


def _when(candidate: Dict[str, Any]) -> str:
    observed = candidate.get('observed_at')
    return observed.date().isoformat() if hasattr(observed, 'date') else 'undated'
