"""Events from what a vendor announced on its own channels.

``market_post_review`` has already read every vendor LinkedIn post once and
given it a verdict and a kind — signal, commentary or noise, and launch,
hiring, partnership and so on. That judgement is reusable, so this extractor
costs nothing and re-reads nothing.

Everything produced here starts at ``vendor_claim``. The company said it; that
is all a company saying it establishes. If a trade publication later reports
the same launch, the fingerprint matches, the evidence merges and the
corroboration rises to ``single_source`` on its own — without replacing the
original post, which remains the first place we saw it.

Three kinds are not events. An award, a research write-up and "other" describe
what a post *is* rather than something that happened to the company, and
forcing them into an event type would fill the timeline with publications.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from sqlalchemy import text

from app.services import entity_events

logger = logging.getLogger(__name__)

# Reviewer kind -> event type. Kinds absent here are deliberately not events.
KIND_TO_EVENT = {
    'launch': 'product_launch',
    'hiring': 'hiring_spike',
    'partnership': 'partnership',
    'customer': 'customer_win',
    'funding': 'funding_round',
    'acquisition': 'acquisition',
}

NOT_EVENTS = {'award', 'research', 'other', 'event', 'opinion'}


def _parsed(value: Optional[str]) -> Optional[datetime]:
    """Article dates are TEXT in this schema, and not always parseable."""
    if not value:
        return None
    raw = str(value).strip().replace('Z', '+00:00')
    for attempt in (raw, raw[:19]):
        try:
            parsed = datetime.fromisoformat(attempt)
            return parsed if parsed.tzinfo else parsed.replace(
                tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


def run(conn, *, brand_id: Optional[int] = None,
        limit: Optional[int] = None) -> Dict[str, Any]:
    where = ["ma.review_verdict = 'signal'", "l.channel IN ('owned_social','owned_web')"]
    params: Dict[str, Any] = {'lim': limit or 5000}
    if brand_id is not None:
        where.append('l.brand_id = :brand_id')
        params['brand_id'] = brand_id

    rows = conn.execute(text(f"""
        SELECT ma.article_uri, ma.review_kind, ma.review_reason,
               l.brand_id, a.title, a.summary, a.publication_date,
               a.news_source, a.url, a.bias_source, b.display_name
          FROM bw_market_articles ma
          JOIN bw_entity_content_links l ON l.article_uri = ma.article_uri
          JOIN articles a ON a.uri = ma.article_uri
          JOIN bw_brands b ON b.id = l.brand_id
         WHERE {' AND '.join(where)}
         ORDER BY ma.article_uri
         LIMIT :lim
    """), params).mappings().all()

    created = merged = skipped = 0
    unmapped: Dict[str, int] = {}
    for row in rows:
        kind = (row['review_kind'] or '').lower()
        event_type = KIND_TO_EVENT.get(kind)
        if event_type is None:
            skipped += 1
            if kind not in NOT_EVENTS:
                unmapped[kind] = unmapped.get(kind, 0) + 1
            continue

        published = _parsed(row['publication_date'])
        outcome = entity_events.record(
            conn,
            event_type=event_type,
            title=(row['title'] or f'{row["display_name"]} {kind}')[:500],
            description=(row['summary'] or row['review_reason'] or '')[:2000],
            brand_ids={int(row['brand_id']): 'subject'},
            attributes={'reviewer_kind': kind, 'announced_by': 'vendor'},
            # The post's own date is when the company said it. That is a real
            # date, and it is what the timeline should show.
            occurred_at=published, precision='day' if published else 'unknown',
            published_at=published,
            subtype=kind,
            evidence=[{
                'evidence_type': 'article',
                'article_uri': row['article_uri'],
                'relationship': 'originates',
                'independence_key': entity_events.independence_key_for_article(
                    row['news_source'], row['url'], row['bias_source']),
                'excerpt': (row['summary'] or row['title'] or '')[:1000],
            }])
        created += 1 if outcome['created'] else 0
        merged += 0 if outcome['created'] else 1

    return {'candidates': len(rows), 'created': created, 'merged': merged,
            'skipped_not_an_event': skipped, 'unmapped_kinds': unmapped}
