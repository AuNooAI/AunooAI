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

An award and "other" are not events. They describe what a post *is* rather than
something that happened to the company, and forcing them into an event type
would fill the timeline with publications.

Research used to sit with them, on the same reasoning, and the reasoning was
sound for the market this was written against: 43 of the 93 developments in a
recent 30-day AI-SOC window would have been vendor research posts, most of them
a benchmark published as content marketing. It is wrong for a market where
evidence *is* the news. On a health tenant "Weight Watchers Releases GLP-1
Results Report Demonstrating 61% Greater Weight Loss" is the most consequential
thing that vendor did that month, and it had nowhere to go.

So research is an event now, and carries the lowest rank in the canonical set,
which keeps it off the report's lead while letting it be recorded, corroborated
and counted.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional, Tuple

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
    # Arrival verbs first in intent, though order here does not decide the
    # winner — the earliest matching sentence does. A post that announces a
    # hire and closes with "P.S. We're hiring" used to title on the P.S.:
    # "Kai Security: We're hiring: https://bit.ly/4vn6KtT" instead of
    # "Thomas N. joins Kai as VP of Product Marketing".
    'hiring': ('joins ', 'joined ', 'welcome ', 'welcoming ', 'is joining',
               'hiring', 'join our team', 'we are looking for', 'open role',
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


# An abbreviation that ends in a full stop but not a sentence. Splitting on
# one decapitates the sentence, and the subject is the first casualty: the
# post "Coalition, Inc. acquired us for our ability to stop cyber threats"
# split after "Inc.", the extractor took the remainder as the news and
# prefixed the vendor it belongs to, and the report read "Wirespeed: acquired
# us…" — the opposite of what happened. A list is cheaper than a segmenter
# and fixes the case that actually bit.
_ABBREV_END = re.compile(
    r'(?:\b(?:Inc|Ltd|Co|Corp|Corp|LLC|LLP|PLC|Plc|GmbH|AG|NV|BV|AB|Oy|SA|SAS|Pty|'
    r'Mr|Mrs|Ms|Dr|Prof|Sr|Jr|St|Mt|Ave|Rd|No|Fig|vs|etc|al|approx)'
    r'|\b[A-Z]|\b(?:e\.g|i\.e|U\.S|U\.K|a\.m|p\.m))\.$')


def _sentences(text_blob: str) -> list:
    """Split on sentence ends, keeping it simple.

    A real segmenter would be a dependency and a model's worth of latency for
    a headline. The one case worth handling without one is an abbreviation
    before the subject's verb, because splitting there changes who did what.
    """
    parts = re.split(r'(?<=[.!?])\s+|\n+', text_blob or '')
    out: list = []
    for part in parts:
        part = part.strip()
        if not part:
            continue
        if out and _ABBREV_END.search(out[-1]):
            out[-1] = out[-1] + ' ' + part
        else:
            out.append(part)
    return out


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
        # A link is not a headline. "We're hiring: https://bit.ly/4vn6KtT"
        # clears the length bar on the URL alone, and the URL is the half a
        # reader cannot use.
        if len(re.sub(r'https?://\S+', '', cleaned).strip()) < 30:
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


# ---------------------------------------------------------------------------
# When it happened, when the post says so
# ---------------------------------------------------------------------------
#
# A vendor post is dated when it was posted, and most of the time that is when
# the news happened. Not always: Prophet Security's 7 Oct 2026 blog post
# "Accelerating the Agentic AI SOC Movement with Amex Ventures and Citi
# Ventures" opens "On February 25, 2026, we announced…", and became a funding
# round dated 8 October. The summary the page carries was written from the
# post and dropped the date, so the only place the real date exists is the
# announcing sentence of the post itself. When that sentence states a calendar
# date well before the post, the event takes that date.
#
# Only the announcing sentence counts. A post that mentions an older date in
# passing ("since our Series A in July 2025…") while announcing something new
# keeps the post date, because the date is not in the sentence that carries
# the news.

_MONTHS = {m: i + 1 for i, m in enumerate(
    ('jan', 'feb', 'mar', 'apr', 'may', 'jun', 'jul', 'aug', 'sep', 'oct',
     'nov', 'dec'))}
_MONTH_RE = (r'(?:jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)'
             r'(?:[a-z]*)\.?')
_STATED_DATE = re.compile(
    r'\b(?:(?P<d1>\d{1,2})(?:st|nd|rd|th)?\s+(?P<m1>' + _MONTH_RE +
    r'),?\s+(?P<y1>20\d{2})'
    r'|(?P<m2>' + _MONTH_RE + r')\s+(?:(?P<d2>\d{1,2})(?:st|nd|rd|th)?,?\s+)?'
    r'(?P<y2>20\d{2}))\b', re.I)

# A date this much earlier than the post is a look-back, not a slow writer.
LOOK_BACK_DAYS = 30
# Kinds whose announcing sentence dates the thing when it is a look-back.
_DATED_KINDS = frozenset({'funding', 'acquisition', 'partnership', 'customer',
                          'launch'})
# The page is fetched only for a post that just arrived: every earlier post
# already has its event, and this runs over the whole signal set each tick.
_FETCH_WITHIN_DAYS = 3
_FETCH_TIMEOUT = 15.0
_PAGE_CHARS = 30000


def stated_date(sentence: str) -> Optional[Tuple[datetime, str]]:
    """The first calendar date in the sentence, with its precision."""
    if not sentence:
        return None
    match = _STATED_DATE.search(sentence)
    if not match:
        return None
    month_word = (match.group('m1') or match.group('m2') or '')[:3].lower()
    month = _MONTHS.get(month_word)
    year = int(match.group('y1') or match.group('y2'))
    day = match.group('d1') or match.group('d2')
    if not month:
        return None
    try:
        if day:
            return (datetime(year, month, int(day), tzinfo=timezone.utc), 'day')
        return (datetime(year, month, 1, tzinfo=timezone.utc), 'month')
    except ValueError:
        return None


# A line that is nothing but a date is a byline. Webflow and most blog
# platforms print the post's own date under its title, and that is the date the
# company published it even when the feed carries a later edit: Prophet's post
# above has the byline "February 25, 2026" and a feed date of 8 October 2026.
_DATE_LINE = re.compile(r'^\s*(?:(?:mon|tues|wednes|thurs|fri|satur|sun)day,?\s+)?'
                        r'(?P<date>\d{1,2}(?:st|nd|rd|th)?\s+' + _MONTH_RE +
                        r',?\s+20\d{2}|' + _MONTH_RE +
                        r'\s+\d{1,2}(?:st|nd|rd|th)?,?\s+20\d{2})\s*$', re.I)


def byline_date(page_text: str) -> Optional[datetime]:
    """The first line of the page that is only a date — the post's byline."""
    for line in (page_text or '').splitlines():
        match = _DATE_LINE.match(line)
        if match:
            found = stated_date(match.group('date'))
            if found and found[1] == 'day':
                return found[0]
    return None


def look_back_date(body: str, kind: str, published: Optional[datetime]
                   ) -> Optional[Tuple[datetime, str]]:
    """The date the announcing sentence gives, when it is well before the post."""
    if not published:
        return None
    sentence = announcing_sentence(body or '', kind)
    if not sentence:
        return None
    found = stated_date(sentence)
    if not found:
        return None
    when, precision = found
    if when <= published - timedelta(days=LOOK_BACK_DAYS):
        return when, precision
    return None


def _page_text(url: str) -> Optional[str]:
    """The visible text of the post, for the announcing sentence."""
    import httpx

    try:
        with httpx.Client(timeout=_FETCH_TIMEOUT, follow_redirects=True,
                          headers={'User-Agent': 'Mozilla/5.0 (compatible; '
                                                 'AunooMarketMonitor/1.0)'}) as client:
            response = client.get(url)
    except Exception as exc:                                   # noqa: BLE001
        logger.info('owned_post: %s unreachable — %s', url, exc)
        return None
    if response.status_code >= 400:
        return None
    html = response.text[:_PAGE_CHARS * 4]
    html = re.sub(r'<(script|style|noscript)[^>]*>.*?</\1>', ' ', html,
                  flags=re.I | re.S)
    html = re.sub(r'<br\s*/?>|</(p|div|li|h[1-6]|section|article)>', '\n', html,
                  flags=re.I)
    text_blob = re.sub(r'<[^>]+>', ' ', html)
    text_blob = re.sub(r'&nbsp;|&#160;', ' ', text_blob)
    text_blob = re.sub(r'[ \t]+', ' ', text_blob)
    return text_blob[:_PAGE_CHARS]


def dated_from_post(row, kind: str, published: Optional[datetime],
                    now: Optional[datetime] = None
                    ) -> Optional[Tuple[datetime, str]]:
    """A look-back date from the post's own text, or None to keep the post date.

    A LinkedIn post's text is its summary, so that is read directly. A blog
    post's summary is a model's digest and drops dates, so the page itself is
    read — but only for a post that arrived in the last few days, since every
    older post already has its event and this runs over the whole set.
    """
    if kind not in _DATED_KINDS or not published:
        return None
    body = ' '.join(x for x in (row.get('title'), row.get('summary')) if x)
    found = look_back_date(body, kind, published)
    if found:
        return found
    # A blog post's uri is its URL; the url column is often empty for them.
    url = row.get('url') or row.get('article_uri') or ''
    if (row.get('channel') or '') != 'owned_web' or not url.startswith('http'):
        return None
    arrived = _parsed(row.get('submission_date')) or published
    if arrived < (now or datetime.now(timezone.utc)) - timedelta(days=_FETCH_WITHIN_DAYS):
        return None
    page = _page_text(url)
    if not page:
        return None
    found = look_back_date(page, kind, published)
    if found:
        return found
    byline = byline_date(page)
    if byline and byline <= published - timedelta(days=LOOK_BACK_DAYS):
        return byline, 'day'
    return None


# Reviewer kind -> event type. Kinds absent here are deliberately not events.
KIND_TO_EVENT = {
    'launch': 'product_launch',
    'hiring': 'hiring_spike',
    'partnership': 'partnership',
    'customer': 'customer_win',
    'funding': 'funding_round',
    'acquisition': 'acquisition',
    'research': 'research_finding',
    'incident': 'incident',
}

NOT_EVENTS = {'award', 'other', 'event', 'opinion'}

# Reviewer kinds a vendor's blog also uses for other companies' news.
_THIRD_PARTY_KINDS = {'acquisition', 'funding', 'partnership', 'customer'}


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
               ma.review_customer, l.channel,
               l.brand_id, a.title, a.summary, a.publication_date,
               a.submission_date,
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

        # A blog post about another company's deal is the vendor's commentary.
        # D3's "Cribl Just Acquired Radiant Security's AI SOC Technology" was
        # reviewed as an acquisition, and would have become D3's.
        if ((row['bias_source'] or '').startswith('owned:')
                and kind in _THIRD_PARTY_KINDS):
            from app.services.market_assessment import speaks_for_vendor
            if not speaks_for_vendor(
                    row['title'] or '',
                    {'vendors': [{'vendor': row['display_name'],
                                  'brand_id': row['brand_id']}]}):
                skipped += 1
                continue
            # A blog story about a customer it does not name is not news
            # (Nebulock, "When Your Insider Risk Program Is Put to the Test").
            if kind == 'customer' and not (row['review_customer'] or {}).get('name'):
                skipped += 1
                continue

        published = _parsed(row['publication_date'])
        # The post's own date is when the company said it. That is a real
        # date, and it is what the timeline should show — unless the post is
        # a look-back whose announcing sentence dates the thing itself.
        occurred, precision = published, ('day' if published else 'unknown')
        attributes = {'reviewer_kind': kind, 'announced_by': 'vendor'}
        try:
            stated = dated_from_post(row, kind, published)
        except Exception:                                      # noqa: BLE001
            stated = None
        if stated:
            occurred, precision = stated
            attributes['date_stated_in_post'] = True
        outcome = entity_events.record(
            conn,
            event_type=event_type,
            title=_event_title(row, kind),
            description=(row['summary'] or row['review_reason'] or '')[:2000],
            brand_ids={int(row['brand_id']): 'subject'},
            attributes=attributes,
            occurred_at=occurred, precision=precision,
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
