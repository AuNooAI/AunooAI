"""Events from a vendor's own pages changing.

The stored ``material`` flag cannot be used for this. It is computed as
``bool(added or removed)`` and a snapshot is only written when the page hash
changed, so it is true on every diff ever stored — 108 of 108 here. It says a
byte moved, which we already knew.

So this extractor computes its own signal: the word-level difference between
the added and removed text. The stored blobs are whole pages, and two captures
of the same page overlap almost entirely, which means the genuine change is
whatever few words differ. A navigation tweak moves two or three; a new
customer logo, a new price tier or a new job opening moves more.

Only pages where a change means something get events. A blog index changes
whenever a post appears and says nothing about the company beyond "still
blogging", whereas a pricing page changing is the company repricing.

The date comes from the page's ``Last-Modified`` header when the server sends
one, because that is when the page actually changed. Without it the event is
undated — the capture time is when we looked, not when they edited.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import text

from app.services import entity_events

logger = logging.getLogger(__name__)

# Page kind -> the event a change to it represents. Kinds absent here change
# for reasons that are not news about the company.
KIND_TO_EVENT = {
    'pricing': 'pricing_change',
    'customers': 'customer_win',
    'partners': 'partnership',
    'changelog': 'product_launch',
    'press': 'product_launch',
    'news': 'product_launch',
}

# Below this many changed words, a page edit is housekeeping.
MIN_CHANGED_WORDS = 8

_WORD = re.compile(r"[\w''-]+")


def run(conn, *, brand_id: Optional[int] = None,
        limit: Optional[int] = None) -> Dict[str, Any]:
    where = ["s.source = 'vendor_web'", "s.snapshot_type = 'page_state'",
             "s.data->>'kind' = ANY(:kinds)"]
    params: Dict[str, Any] = {'kinds': list(KIND_TO_EVENT),
                              'lim': limit or 2000}
    if brand_id is not None:
        where.append('s.brand_id = :brand_id')
        params['brand_id'] = brand_id

    rows = conn.execute(text(f"""
        SELECT s.id, s.brand_id, s.observed_at, s.data, b.display_name
          FROM bw_vendor_snapshots s
          JOIN bw_brands b ON b.id = s.brand_id
         WHERE {' AND '.join(where)}
         ORDER BY s.id
         LIMIT :lim
    """), params).mappings().all()

    created = merged = below_threshold = 0
    for row in rows:
        data = row['data'] or {}
        diff = data.get('diff') or {}
        changed = _changed_words(diff)
        if len(changed) < MIN_CHANGED_WORDS:
            below_threshold += 1
            continue

        kind = data.get('kind')
        event_type = KIND_TO_EVENT[kind]
        occurred = _last_modified(data.get('last_modified'))
        summary = ' '.join(changed[:40])

        outcome = entity_events.record(
            conn, event_type=event_type,
            title=f"{row['display_name']}: {kind} page changed",
            description=(f"The {kind} page at {data.get('url')} changed. "
                         f"New or removed wording includes: {summary}"),
            brand_ids={int(row['brand_id']): 'subject'},
            attributes={'page_kind': kind, 'url': data.get('url'),
                        'changed_word_count': len(changed),
                        'dated_from': 'last_modified_header' if occurred
                                      else 'not stated by the source'},
            occurred_at=occurred,
            precision='minute' if occurred else 'unknown',
            subtype=kind,
            evidence=[{'evidence_type': 'snapshot',
                       'snapshot_id': int(row['id']),
                       'relationship': 'originates',
                       'independence_key': f"owned:page:{data.get('url')}",
                       'excerpt': summary[:1000]}])
        created += 1 if outcome['created'] else 0
        merged += 0 if outcome['created'] else 1

    return {'pages_examined': len(rows), 'created': created, 'merged': merged,
            'below_change_threshold': below_threshold}


# Above this share of the page, the "change" is not an edit. Either it is the
# first capture or the page was replaced wholesale.
MAX_CHANGE_RATIO = 0.5


def _changed_words(diff: Dict[str, Any]) -> List[str]:
    """Words present on one side of the diff and not the other.

    Two things have to be true before a delta means anything.

    Both sides must exist. The first time a page is captured there is nothing
    to compare it against — ``removed`` is empty and the symmetric difference
    is the entire page, so every page we had never seen before looked like it
    had just changed. Most of this tenant's captures are first sightings.

    And the delta must be a minority of the page. Two captures of one page
    overlap almost completely, so a genuine edit is small. When most of the
    words differ, the page was replaced rather than edited, and calling that a
    pricing change would be a guess about what happened.
    """
    added_blobs = diff.get('added') or []
    removed_blobs = diff.get('removed') or []
    if not added_blobs or not removed_blobs:
        return []

    added_words = _WORD.findall(' '.join(added_blobs).lower())
    removed_words = _WORD.findall(' '.join(removed_blobs).lower())
    added_set, removed_set = set(added_words), set(removed_words)
    delta = added_set ^ removed_set
    union = added_set | removed_set
    if not union or len(delta) / len(union) > MAX_CHANGE_RATIO:
        return []
    # Distinct words, in reading order. Counting repeats let a menu item
    # appearing three times read as three changed words, so "glossary
    # glossary glossary" cleared the threshold on its own.
    ordered: List[str] = []
    seen = set()
    for word in added_words + removed_words:
        if word in delta and word not in seen:
            seen.add(word)
            ordered.append(word)
    return ordered[:200]


def _last_modified(raw: Optional[str]) -> Optional[datetime]:
    if not raw:
        return None
    try:
        parsed = parsedate_to_datetime(raw)
    except (TypeError, ValueError):
        return None
    if parsed is None:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
