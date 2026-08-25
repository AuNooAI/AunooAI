"""The social feed, read per company instead of per topic.

The existing feed selects posts by the topic string they were collected under
and reports the relevance and sentiment stored on the article row. That works
for one brand watching one topic and breaks in two ways the moment it is not.

A post naming two companies has one article row, so whichever company was
scored last owns the verdict for both. And a post collected under a market's
theme topic — "agentic SOC", "alert triage" — has no company attached at all,
so it never appears in any company's feed however clearly it names one.

Reading from ``bw_entity_mentions`` fixes both, because the relevance and
sentiment belong to the pair of (post, company) rather than to the post.

Three distinctions the old shape could not make are carried here.

**Owned content is separated from what other people said.** A vendor's own
LinkedIn post is in the feed — an operator wants to see it — but it is marked
``owned_claim`` and is excluded from the sentiment rollup, because a company
praising itself is not evidence anyone else did.

**Unevaluated is not neutral.** A mention nobody has scored is counted in its
own bucket rather than folded into the sentiment split, so a feed cannot report
a settled balance of opinion assembled from posts no one read.

**Empty is stated as a coverage gap.** Zero external mentions means we did not
collect any, which is not the same as nobody having spoken, and the response
says which.

The topic parameters still work. They are resolved to companies here so the
existing UI keeps functioning during rollout rather than needing to change on
the same day the flag flips.
"""

from __future__ import annotations

import json
import logging
from collections import Counter
from typing import Any, Dict, List, Optional

from sqlalchemy import text

logger = logging.getLogger(__name__)

# Channels that are the company speaking. Present in the feed, absent from the
# sentiment denominator.
OWNED_CHANNELS = ('owned_web', 'owned_social')

# What the old ``source`` parameter meant, mapped onto platforms. LinkedIn is
# owned company posts only — nothing collects public LinkedIn mentions.
SOURCE_PLATFORMS = {
    'reddit': ['reddit'],
    'bluesky': ['bluesky'],
    'twitter': ['twitter'],
    'x': ['twitter'],
    'instagram': ['instagram'],
    'tiktok': ['tiktok'],
    'linkedin': ['linkedin'],
}


def brands_for_topics(conn, topics: Optional[str]) -> List[int]:
    """Resolve the legacy topic strings to companies.

    Topics are named ``Brand Monitoring <display name>``, so the company is
    recoverable without changing any caller. A topic that names no known
    company resolves to nothing rather than to everything.
    """
    if not topics:
        return []
    names = []
    for raw in topics.split(','):
        name = raw.strip()
        if not name:
            continue
        for prefix in ('Brand Monitoring ', 'Market Monitoring '):
            if name.startswith(prefix):
                name = name[len(prefix):]
                break
        names.append(name)
    if not names:
        return []
    rows = conn.execute(text("""
        SELECT id FROM bw_brands WHERE display_name = ANY(:names)
    """), {'names': names}).fetchall()
    return [int(r[0]) for r in rows]


def social_feed(conn, *, brand_ids: List[int], days_back: int = 30,
                min_relevance: float = 0.0, source: Optional[str] = None,
                keyword: Optional[str] = None,
                start_date: Optional[str] = None,
                end_date: Optional[str] = None,
                include_unevaluated: bool = True,
                include_owned: bool = False,
                include_flagged: bool = False,
                limit: int = 100) -> Dict[str, Any]:
    """Per-company social mentions, in the shape the existing tab expects."""
    if not brand_ids:
        return _empty(days_back, min_relevance, include_unevaluated, keyword,
                      'no company was resolved from the requested topics')

    where = ['m.brand_id = ANY(:brands)']
    params: Dict[str, Any] = {'brands': brand_ids, 'lim': limit}

    if include_owned:
        where.append("m.channel IN ('public_social','community','employee',"
                     "'owned_social','owned_web')")
    else:
        where.append("m.channel IN ('public_social','community','employee')")

    if source:
        platforms = SOURCE_PLATFORMS.get(source.strip().lower())
        if platforms:
            where.append('m.platform = ANY(:platforms)')
            params['platforms'] = platforms

    if start_date or end_date:
        window_start = start_date or '1900-01-01'
        window_end = (end_date or '9999-12-31') + 'T23:59:59'
    else:
        window_start, window_end = _window(conn, days_back)
    where.append('a.publication_date >= :start AND a.publication_date <= :end')
    params['start'] = window_start
    params['end'] = window_end

    # A threshold means "evaluated and at least this", so unscored mentions
    # drop out the moment any minimum is asked for.
    if min_relevance > 0:
        where.append('m.relevance >= :min_rel')
        params['min_rel'] = min_relevance
    elif not include_unevaluated:
        where.append('m.relevance IS NOT NULL')

    if not include_flagged:
        where.append("m.status <> 'false_positive'")
        where.append('NOT EXISTS (SELECT 1 FROM bw_finding_reviews r '
                     "WHERE r.article_uri = m.article_uri "
                     "AND r.status = 'false_positive')")

    rows = conn.execute(text(f"""
        SELECT m.id, m.brand_id, m.article_uri, m.channel, m.platform,
               m.relevance, m.sentiment, m.stance, m.status, m.excerpt,
               m.evaluated_at, m.mention_type,
               a.title, a.summary, a.news_source, a.publication_date, a.topic,
               a.social_meta,
               b.display_name,
               t.term AS matched_term,
               sa.handle AS author_handle,
               si.relationship AS author_relationship,
               si.status AS author_identity_status
          FROM bw_entity_mentions m
          JOIN articles a ON a.uri = m.article_uri
          JOIN bw_brands b ON b.id = m.brand_id
          LEFT JOIN bw_entity_query_terms t ON t.id = m.matched_query_term_id
          LEFT JOIN bw_entity_content_links l ON l.id = m.content_link_id
          LEFT JOIN social_accounts sa ON sa.id = l.social_account_id
          LEFT JOIN bw_entity_social_identities si
                 ON si.social_account_id = sa.id AND si.brand_id = m.brand_id
                AND si.valid_to IS NULL
         WHERE {' AND '.join(where)}
         ORDER BY a.publication_date DESC
         LIMIT :lim
    """), params).mappings().all()

    posts = [_post(row) for row in rows]

    if keyword:
        wanted = keyword.strip().lower()
        posts = [p for p in posts
                 if (p['matched_keywords']
                     and any(k.lower() == wanted for k in p['matched_keywords']))]

    return _rollup(posts, days_back, min_relevance, include_unevaluated, keyword)


def _post(row) -> Dict[str, Any]:
    meta = row['social_meta']
    if isinstance(meta, str):
        try:
            meta = json.loads(meta)
        except ValueError:
            meta = None
    owned = row['channel'] in OWNED_CHANNELS
    return {
        'mention_id': int(row['id']),
        'brand_id': int(row['brand_id']),
        'brand': row['display_name'],
        'uri': row['article_uri'],
        'title': row['title'],
        'summary': row['summary'],
        'news_source': row['news_source'],
        'platform': row['platform'] or 'social',
        'channel': row['channel'],
        'publication_date': str(row['publication_date'])
                            if row['publication_date'] else None,
        'relevance': round(float(row['relevance']), 3)
                     if row['relevance'] is not None else None,
        'sentiment': row['sentiment'],
        'stance': row['stance'],
        # An operator needs to see at a glance whether this is the company
        # talking or somebody else.
        'is_owned': owned,
        'evaluated': row['evaluated_at'] is not None,
        'status': row['status'],
        'excerpt': row['excerpt'],
        'topic': row['topic'],
        'social_meta': meta if isinstance(meta, dict) else None,
        'matched_keywords': [row['matched_term']] if row['matched_term'] else [],
        'author': {
            'handle': row['author_handle'],
            'relationship': row['author_relationship'],
            'identity_status': row['author_identity_status'],
        } if row['author_handle'] else None,
    }


def _rollup(posts: List[Dict[str, Any]], days_back: int, min_relevance: float,
            include_unevaluated: bool, keyword: Optional[str]) -> Dict[str, Any]:
    external = [p for p in posts if not p['is_owned']]
    owned = [p for p in posts if p['is_owned']]
    evaluated = [p for p in external if p['evaluated']]

    # Sentiment counts only what was actually judged, and only what somebody
    # other than the company said.
    sentiment = Counter((p['sentiment'] or 'Unrated') for p in evaluated)
    platforms = Counter(p['platform'] for p in posts)
    channels = Counter(p['channel'] for p in posts)
    keywords = Counter(k for p in posts for k in p['matched_keywords'])

    notes: List[str] = []
    if not external:
        notes.append('No external mentions in this window. That is a gap in '
                     'collection, not evidence that nobody discussed this '
                     'company.')
    unevaluated = len(external) - len(evaluated)
    if unevaluated:
        notes.append(f'{unevaluated} external mention(s) have not been '
                     f'evaluated and are excluded from the sentiment split.')

    return {
        'window_days': days_back,
        'min_relevance': min_relevance,
        'include_unevaluated': include_unevaluated,
        'keyword': keyword,
        'total': len(posts),
        'evaluated': len(evaluated),
        'by_platform': dict(platforms),
        'by_sentiment': dict(sentiment),
        'by_keyword': dict(keywords.most_common()),
        'posts': posts,
        # New, and the reason for the change: these three were impossible to
        # separate when the score lived on the article row.
        'by_channel': dict(channels),
        'external_total': len(external),
        'owned_total': len(owned),
        'unevaluated_total': unevaluated,
        'sentiment_denominator': len(evaluated),
        'coverage_notes': notes,
        'read_path': 'entity_mentions',
    }


def _empty(days_back: int, min_relevance: float, include_unevaluated: bool,
           keyword: Optional[str], why: str) -> Dict[str, Any]:
    return {
        'window_days': days_back, 'min_relevance': min_relevance,
        'include_unevaluated': include_unevaluated, 'keyword': keyword,
        'total': 0, 'evaluated': 0, 'by_platform': {}, 'by_sentiment': {},
        'by_keyword': {}, 'posts': [], 'by_channel': {}, 'external_total': 0,
        'owned_total': 0, 'unevaluated_total': 0, 'sentiment_denominator': 0,
        'coverage_notes': [why], 'read_path': 'entity_mentions',
    }


def _window(conn, days_back: int) -> tuple:
    row = conn.execute(text("""
        SELECT to_char(NOW() - CAST(:d || ' days' AS INTERVAL),
                       'YYYY-MM-DD') AS start,
               to_char(NOW(), 'YYYY-MM-DD"T"HH24:MI:SS') AS finish
    """), {'d': str(days_back)}).mappings().first()
    return row['start'], row['finish']
