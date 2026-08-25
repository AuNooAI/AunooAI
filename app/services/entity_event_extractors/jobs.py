"""Events from hiring, counted as a pattern rather than a list of postings.

One job advert is not an event. A company opening several roles in the same
function, or hiring into a country it had no presence in, is — and the
difference is the whole reason this reads the postings in aggregate instead of
emitting one event per row, which would bury a timeline under recruitment.

Two patterns are extracted. A **hiring spike** is several distinct postings in
one function inside a short window. A **geographic expansion** is a posting in
a country where this company has never posted before, which is a weaker signal
and is marked as such in the attributes rather than asserted as a new office.

Dates here are real: LinkedIn gives each posting its own date, so the spike is
dated to the most recent posting in it.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import text

from app.services import entity_events

logger = logging.getLogger(__name__)

# Distinct postings in one function within the window to count as a spike.
SPIKE_THRESHOLD = 3
SPIKE_WINDOW = timedelta(days=30)


def _parsed(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    raw = str(value).strip().replace('Z', '+00:00')
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _country(location: Optional[str]) -> Optional[str]:
    """The last comma-separated part of a LinkedIn location string."""
    if not location:
        return None
    return location.split(',')[-1].strip() or None


def run(conn, *, brand_id: Optional[int] = None,
        limit: Optional[int] = None) -> Dict[str, Any]:
    where = ["source = 'linkedin_jobs'", "snapshot_type = 'job_posting'"]
    params: Dict[str, Any] = {'lim': limit or 5000}
    if brand_id is not None:
        where.append('brand_id = :brand_id')
        params['brand_id'] = brand_id

    rows = conn.execute(text(f"""
        SELECT id, brand_id, data FROM bw_vendor_snapshots
         WHERE {' AND '.join(where)}
         ORDER BY id LIMIT :lim
    """), params).mappings().all()

    postings: Dict[int, List[Dict[str, Any]]] = defaultdict(list)
    for row in rows:
        data = row['data'] or {}
        postings[int(row['brand_id'])].append({
            'snapshot_id': int(row['id']),
            'posting_id': data.get('posting_id'),
            'function': (data.get('function') or 'unspecified').strip(),
            'title': data.get('title'),
            'location': data.get('location'),
            'country': _country(data.get('location')),
            'posted_at': _parsed(data.get('posted_date')),
        })

    created = merged = spikes = expansions = 0
    for brand, items in postings.items():
        name = conn.execute(text(
            'SELECT display_name FROM bw_brands WHERE id = :b'),
            {'b': brand}).scalar() or f'brand {brand}'

        by_function: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        for item in items:
            by_function[item['function']].append(item)

        for function, group in by_function.items():
            dated = [g for g in group if g['posted_at']]
            if len(dated) < SPIKE_THRESHOLD:
                continue
            dated.sort(key=lambda g: g['posted_at'])
            latest = dated[-1]['posted_at']
            window = [g for g in dated if latest - g['posted_at'] <= SPIKE_WINDOW]
            distinct = {g['posting_id'] for g in window if g['posting_id']}
            if len(distinct) < SPIKE_THRESHOLD:
                continue

            locations = sorted({g['location'] for g in window if g['location']})
            outcome = entity_events.record(
                conn, event_type='hiring_spike',
                title=(f'{name}: {len(distinct)} open {function} roles'),
                description=(f'{len(distinct)} distinct {function} postings '
                             f'within {SPIKE_WINDOW.days} days. Locations: '
                             f'{", ".join(locations) or "not stated"}.'),
                brand_ids={brand: 'subject'},
                attributes={'function': function, 'postings': len(distinct),
                            'locations': locations},
                occurred_at=latest, precision='day', subtype=function,
                evidence=[{'evidence_type': 'snapshot',
                           'snapshot_id': g['snapshot_id'],
                           'relationship': 'supports',
                           'independence_key':
                               entity_events.independence_key_for_source('linkedin_jobs'),
                           'excerpt': g['title']} for g in window[:20]])
            created += 1 if outcome['created'] else 0
            merged += 0 if outcome['created'] else 1
            spikes += 1

        # A first posting in a country is a hint, not a announcement of an
        # office, and the attributes say so.
        countries = defaultdict(list)
        for item in items:
            if item['country']:
                countries[item['country']].append(item)
        if len(countries) > 1:
            for country, group in countries.items():
                dated = [g for g in group if g['posted_at']]
                if not dated or len(group) > 2:
                    continue
                newest = max(dated, key=lambda g: g['posted_at'])
                outcome = entity_events.record(
                    conn, event_type='geographic_expansion',
                    title=f'{name}: hiring in {country}',
                    description=(f'{len(group)} posting(s) located in '
                                 f'{country}. A posting is evidence of hiring '
                                 f'there, not of an office being opened.'),
                    brand_ids={brand: 'subject'},
                    attributes={'country': country, 'postings': len(group),
                                'strength': 'weak: inferred from job location'},
                    occurred_at=newest['posted_at'], precision='day',
                    subtype=country,
                    evidence=[{'evidence_type': 'snapshot',
                               'snapshot_id': g['snapshot_id'],
                               'relationship': 'supports',
                               'independence_key':
                               entity_events.independence_key_for_source('linkedin_jobs'),
                               'excerpt': g['title']} for g in group[:10]])
                created += 1 if outcome['created'] else 0
                merged += 0 if outcome['created'] else 1
                expansions += 1

    return {'postings_read': len(rows), 'created': created, 'merged': merged,
            'hiring_spikes': spikes, 'geographic_hints': expansions}
