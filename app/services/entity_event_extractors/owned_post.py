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
import re
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from sqlalchemy import text

from app.services import entity_events

logger = logging.getLogger(__name__)

# Words that mark the sentence actually carrying the announcement, per kind.
# A vendor post opens with a hook and states its news two or three sentences
# down, so the first line is almost never the news: a real Booz Allen Hamilton
# partnership was titled "Security operations are being asked to move at
# machine speed", which names neither the partner nor the partnership.
_KIND_MARKERS = {
    'launch': ('launch', 'announc', 'unveil', 'introduc', 'now available',
               'released', 'releasing', 'general availability', 'we built',
               'we created', 'new '),
    'partnership': ('partner', 'alliance', 'teaming', 'join forces',
                    'collaborat', 'integrat', 'founding member'),
    'customer': ('customer', 'client', 'chose', 'selected', 'deployed',
                 'case study', 'is now using', 'trusted by'),
    'funding': ('raise', 'raised', 'funding', 'series ', 'seed', 'led by',
                'investment', 'backed by'),
    'acquisition': ('acquir', 'acquisition', 'has been acquired', 'merge'),
    'hiring': ('hiring', 'join our team', 'we are looking for', 'open role',
               "we're growing", 'growing our team'),
}

# Sentences that point at the news without stating it. "Read the logic behind
# the new standard", "dive into the details of our official announcement below"
# and "We built X around that question" all match a kind marker and then tell
# the reader nothing: the referent is somewhere else. Falling back to the post's
# own title is better than a headline that defers.
_DEFERRING_OPENERS = (
    'read ', 'dive into', 'check out', 'learn more', 'see how', 'see what',
    'watch ', 'find out', 'discover how', 'join us', 'register', 'sign up',
    'more on', 'details ', 'full story', 'link in',
)
_DEFERRING_ANYWHERE = (
    'in the comments', 'at the link', 'link below', 'below.', 'link in bio',
    'that question', 'this question',
)

# A headline, not a paragraph. Long enough for a counterparty and a reason.
_TITLE_CHARS = 200


def _sentences(text_blob: str) -> list:
    """Split on sentence ends, keeping it dumb on purpose.

    A real segmenter would handle "Inc." and "e.g." better, and would be a
    dependency and a model's worth of latency for a headline.
    """
    import re

    parts = re.split(r'(?<=[.!?])\s+|\n+', text_blob or '')
    return [p.strip() for p in parts if p and p.strip()]


def announcing_sentence(body: str, kind: str) -> Optional[str]:
    """The sentence that states the news, or None if none stands out.

    Returns None rather than a guess: falling back to the post's own title is
    no worse than today, and inventing a headline from a sentence that does not
    contain the news would be.
    """
    markers = _KIND_MARKERS.get((kind or '').lower())
    if not markers or not body:
        return None
    for sentence in _sentences(body):
        low = sentence.lower()
        if not any(m in low for m in markers):
            continue
        # An opener that only sets up the news is not the news. "That's why"
        # and friends are common in exactly this position.
        cleaned = re.sub(r'^(and|but|so|that\u2019s why|that\'s why|which is why)\s+',
                         '', sentence, flags=re.I).strip()
        if len(cleaned) < 30:
            continue
        low_clean = cleaned.lower()
        if low_clean.startswith(_DEFERRING_OPENERS):
            continue
        if any(marker in low_clean for marker in _DEFERRING_ANYWHERE):
            continue
        if len(cleaned) <= _TITLE_CHARS:
            return cleaned
        # Trim on a word boundary rather than mid-word.
        cut = cleaned[:_TITLE_CHARS].rsplit(' ', 1)[0]
        return cut.rstrip(',;:') + '\u2026'
    return None


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


def _event_title(row, kind: str) -> str:
    """Vendor name, then the sentence that states the news.

    Falls back to the post's own title when no sentence carries the kind's
    markers, so this is never worse than what it replaced.
    """
    name = row['display_name']
    sentence = announcing_sentence(row['summary'] or '', kind)
    if not sentence:
        return (row['title'] or f'{name} {kind}')[:500]

    # Leading decoration is not a headline. Vendor posts open with rockets and
    # flames often enough that stripping them is worth the two lines.
    sentence = re.sub(r'^[^\w(\u201c"\u2018\']+', '', sentence).strip()

    # "Dropzone AI: Dropzone AI is a founding member" — when the sentence
    # already opens with the company, the prefix is noise.
    if sentence.lower().startswith(name.lower()):
        return sentence[:500]
    return f'{name}: {sentence}'[:500]


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
            title=_event_title(row, kind),
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

    # Fold the same announcement said twice. Runs after, not during: a vendor's
    # second post about one partnership is only recognisable once both events
    # exist, and reconciling is cheaper than making the fingerprint understand
    # restatement.
    dupes = entity_events.merge_duplicates(conn)

    return {'candidates': len(rows), 'created': created, 'merged': merged,
            'duplicates_folded': dupes['merged'],
            'skipped_not_an_event': skipped, 'unmapped_kinds': unmapped}
