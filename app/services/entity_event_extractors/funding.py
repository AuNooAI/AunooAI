"""Events from funding facts changing.

A round type moving from seed to series_a, or a status moving from Undisclosed
to Disclosed, is the visible trace of a raise. The raise itself has a date the
provider usually does not give us, so these events are undated unless a total
also changed and carried one.

The dollar total is handled with more suspicion than the stage. Totals only go
up, so a smaller figure is a correction or a mistake rather than news — the
resolver already refuses to move the canonical value for one, and this
extractor will not announce one either. What it will do is record a rise, which
is the shape of an actual raise.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from sqlalchemy import text

from app.services import entity_events

logger = logging.getLogger(__name__)

WATCHED = ('last_funding_type', 'funding_status', 'funding_total_musd')


def run(conn, *, brand_id: Optional[int] = None,
        limit: Optional[int] = None) -> Dict[str, Any]:
    where = ['field_key = ANY(:fields)']
    params: Dict[str, Any] = {'fields': list(WATCHED), 'lim': limit or 5000}
    if brand_id is not None:
        where.append('brand_id = :brand_id')
        params['brand_id'] = brand_id

    rows = conn.execute(text(f"""
        SELECT id, brand_id, field_key, source, value_text, value_number,
               observed_at,
               LAG(value_text)   OVER w AS prev_text,
               LAG(value_number) OVER w AS prev_number,
               LAG(id)           OVER w AS prev_id,
               LAG(observed_at)  OVER w AS prev_observed_at
          FROM bw_entity_observations
         WHERE {' AND '.join(where)}
           AND status = 'active' AND market_id IS NULL
        WINDOW w AS (PARTITION BY brand_id, field_key, source
                     ORDER BY observed_at, id)
         LIMIT :lim
    """), params).mappings().all()

    created = merged = ignored_decrease = 0
    for row in rows:
        if row['prev_id'] is None:
            continue

        if row['field_key'] == 'funding_total_musd':
            old, new = row['prev_number'], row['value_number']
            if old is None or new is None or float(new) <= float(old):
                # A total that fell is a correction, and the resolver has
                # already declined to act on it. Announcing it would be worse.
                ignored_decrease += 1 if (old is not None and new is not None
                                          and float(new) < float(old)) else 0
                continue
            title = f'total funding rose from ${old}m to ${new}m'
            attrs = {'from_musd': float(old), 'to_musd': float(new)}
        else:
            old, new = row['prev_text'], row['value_text']
            if not old or not new or old == new:
                continue
            title = f'{row["field_key"].replace("_", " ")} changed from {old} to {new}'
            attrs = {'from': old, 'to': new}

        name = conn.execute(text(
            'SELECT display_name FROM bw_brands WHERE id = :b'),
            {'b': row['brand_id']}).scalar() or f"brand {row['brand_id']}"

        outcome = entity_events.record(
            conn, event_type='funding_round',
            title=f'{name}: {title}',
            description=(f"{row['source']} reported a change in "
                         f"{row['field_key']}. The date of the round itself is "
                         f"not given by this source."),
            brand_ids={int(row['brand_id']): 'subject'},
            attributes={'field': row['field_key'], 'source': row['source'],
                        'observed_between': [
                            row['prev_observed_at'].isoformat(),
                            row['observed_at'].isoformat()],
                        **attrs},
            occurred_at=None, precision='unknown',
            subtype=row['field_key'],
            evidence=[{'evidence_type': 'observation',
                       'observation_id': int(row['id']),
                       'relationship': 'supports',
                       'independence_key': entity_events.independence_key_for_source(row["source"])}])
        created += 1 if outcome['created'] else 0
        merged += 0 if outcome['created'] else 1

    return {'readings_compared': len(rows), 'created': created,
            'merged': merged, 'ignored_total_decrease': ignored_decrease}
