"""Events from a company fact changing between two readings.

Headcount moving from 122 to 145, a status going from active to acquired, a
company rewriting how it describes itself: each is a change worth a line on a
timeline, and each is visible by comparing consecutive observations of the same
field from the same source.

The comparison is per source on purpose. LinkedIn's employee count and a
verified total workforce figure measure different things, so a step between
them is a change of source rather than a change in the company, and treating it
as news would put a fictional event on the page every time a better source
arrived.

These events carry **no date**. A headcount that moved between two readings a
month apart moved on some day nobody recorded. The reading dates bound the
change and are kept in ``attributes`` as ``observed_between``, which is the
true and useful statement; stamping the event with the day the later reading
landed would assert something we do not know.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from sqlalchemy import text

from app.services import entity_events

logger = logging.getLogger(__name__)

# field -> (event type, how much movement is worth reporting)
WATCHED = {
    'employee_count': ('headcount_change', 0.10),
    'operating_status': ('operating_status_change', None),
    'description': ('brand_identity_change', None),
}


def run(conn, *, brand_id: Optional[int] = None,
        limit: Optional[int] = None) -> Dict[str, Any]:
    where = ['field_key = ANY(:fields)']
    params: Dict[str, Any] = {'fields': list(WATCHED), 'lim': limit or 5000}
    if brand_id is not None:
        where.append('brand_id = :brand_id')
        params['brand_id'] = brand_id

    # Consecutive readings of one field from one source, oldest first.
    rows = conn.execute(text(f"""
        SELECT id, brand_id, field_key, source, value_text, value_number,
               observed_at,
               LAG(value_text)   OVER w AS prev_text,
               LAG(value_number) OVER w AS prev_number,
               LAG(observed_at)  OVER w AS prev_observed_at,
               LAG(id)           OVER w AS prev_id
          FROM bw_entity_observations
         WHERE {' AND '.join(where)}
           AND status = 'active' AND market_id IS NULL
        WINDOW w AS (PARTITION BY brand_id, field_key, source
                     ORDER BY observed_at, id)
         LIMIT :lim
    """), params).mappings().all()

    created = merged = 0
    for row in rows:
        if row['prev_id'] is None:
            continue                      # first reading is not a change
        event_type, threshold = WATCHED[row['field_key']]
        change = _describe(row, threshold)
        if change is None:
            continue

        name = conn.execute(text(
            'SELECT display_name FROM bw_brands WHERE id = :b'),
            {'b': row['brand_id']}).scalar() or f"brand {row['brand_id']}"

        outcome = entity_events.record(
            conn, event_type=event_type,
            title=f"{name}: {change['title']}",
            description=change['description'],
            brand_ids={int(row['brand_id']): 'subject'},
            attributes={'field': row['field_key'], 'source': row['source'],
                        'from': change['from'], 'to': change['to'],
                        'observed_between': [
                            row['prev_observed_at'].isoformat(),
                            row['observed_at'].isoformat()]},
            # Deliberately undated: see the module docstring.
            occurred_at=None, precision='unknown',
            evidence=[
                {'evidence_type': 'observation',
                 'observation_id': int(row['id']),
                 'relationship': 'supports',
                 'independence_key': entity_events.independence_key_for_source(row["source"])},
                {'evidence_type': 'observation',
                 'observation_id': int(row['prev_id']),
                 'relationship': 'context',
                 'independence_key': entity_events.independence_key_for_source(row["source"])},
            ])
        created += 1 if outcome['created'] else 0
        merged += 0 if outcome['created'] else 1

    return {'readings_compared': len(rows), 'created': created, 'merged': merged}


def _describe(row, threshold: Optional[float]) -> Optional[Dict[str, Any]]:
    """What changed, or None when the movement is not worth reporting."""
    if row['field_key'] == 'employee_count':
        old, new = row['prev_number'], row['value_number']
        if old is None or new is None or old == 0:
            return None
        delta = (float(new) - float(old)) / float(old)
        if threshold is not None and abs(delta) < threshold:
            return None
        direction = 'grew' if delta > 0 else 'shrank'
        return {'from': int(old), 'to': int(new),
                'title': f'headcount {direction} from {int(old)} to {int(new)}',
                'description': (f"{row['source']} reported {int(old)} people, "
                                f"then {int(new)}, a change of "
                                f"{delta * 100:.0f}%. The date of the change "
                                f"itself is not recorded by the source.")}

    old_text, new_text = row['prev_text'], row['value_text']
    if not old_text or not new_text or old_text == new_text:
        return None
    if row['field_key'] == 'description':
        # A reworded sentence is not a repositioning; require real divergence.
        if _similar(old_text, new_text) > 0.8:
            return None
        return {'from': old_text[:200], 'to': new_text[:200],
                'title': 'changed how it describes itself',
                'description': (f"Self-description on {row['source']} changed. "
                                f"Previously: {old_text[:300]}")}
    return {'from': old_text, 'to': new_text,
            'title': f'{row["field_key"]} changed from {old_text} to {new_text}',
            'description': (f"{row['source']} reported {row['field_key']} as "
                            f"{old_text}, then {new_text}.")}


def _similar(left: str, right: str) -> float:
    """Word overlap, which is enough to tell an edit from a rewrite."""
    a, b = set(left.lower().split()), set(right.lower().split())
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)
