"""Single source of truth for "is this article row a social post?".

Social posts (Reddit / Bluesky / X / Instagram / TikTok via the xpoz API) live in
the same `articles` table as news, distinguished only by `news_source` naming
conventions: 'xpoz:<platform>', 'bluesky', 'reddit.com', 'bsky*', 'telegram', ...

Historically each consumer hand-rolled its own predicate and they drifted — the
worst case being the social evaluator missing 'xpoz', which left every X/
Instagram/TikTok post unscored and invisible while the alert rules (with their
own, correct predicate) could still count them. Import from here instead:

  - SOCIAL_SOURCES: substrings for parameterized LIKE filters
  - is_social_source(): python-side check
  - social_src_sql(): ready-made SQL predicate for raw queries

Adding a platform = adding one substring here.
"""
import re
from typing import Optional

SOCIAL_SOURCES = ("reddit", "bluesky", "bsky", "xpoz", "telegram")


def is_social_source(news_source: Optional[str]) -> bool:
    s = (news_source or "").lower()
    return any(k in s for k in SOCIAL_SOURCES)


def social_src_sql(column: str = "news_source") -> str:
    """SQL predicate matching social rows, e.g. social_src_sql('a.news_source').

    Values are the static SOCIAL_SOURCES constants (never user input), so
    inlining them as literals is safe and keeps call sites bind-param-free.
    """
    return "(" + " OR ".join(f"LOWER({column}) LIKE '%{k}%'" for k in SOCIAL_SOURCES) + ")"


# ---------------------------------------------------------------------------
# Structured classification, for the entity path
# ---------------------------------------------------------------------------
#
# The substring test above is kept exactly as it is, because seventeen call
# sites depend on its current answers and changing them is not this change's
# job. It does have one known false positive: a domain that merely contains a
# platform name — clsbluesky.law.columbia.edu is a law-school blog, and
# ``is_social_source`` calls it social. Two articles in this tenant are
# affected.
#
# New code classifies instead of testing, because a channel needs more than a
# yes/no. Which platform a post came from, and whether it is the company's own
# announcement or somebody else's opinion, are the two facts that decide
# whether it belongs in reputation sentiment at all.

# Exact news_source values, and the (platform, channel) each one means.
_EXACT = {
    'bluesky': ('bluesky', 'public_social'),
    'reddit': ('reddit', 'community'),
    'reddit.com': ('reddit', 'community'),
    'www.reddit.com': ('reddit', 'community'),
}

# xpoz reports the platform in the suffix. Reddit is a community rather than a
# broadcast network, and the distinction changes how its sentiment reads.
_XPOZ_CHANNEL = {'reddit': 'community'}

OWNED_BIAS_SOURCES = {'vendor:linkedin': ('linkedin', 'owned_social')}

# A company's own publishing, marked in ``articles.bias_source``:
#   owned:<domain>   an article on the company's own website (its blog, its
#                    press page), stamped by app.services.bw_owned
#   vendor:linkedin  the company's own LinkedIn posts (Market Monitor)
# Neither belongs in news sentiment or share of voice: a brand praising itself
# is not coverage. They stay visible in article lists, flagged as owned.
OWNED_BIAS_PREFIXES = ('owned:', 'vendor:')


def is_owned_source(bias_source: Optional[str]) -> bool:
    b = (bias_source or '').strip().lower()
    return any(b.startswith(pfx) for pfx in OWNED_BIAS_PREFIXES)


def owned_src_sql(column: str = "bias_source") -> str:
    """SQL predicate matching a company's own publishing, e.g. owned_src_sql('a.bias_source')."""
    return "(" + " OR ".join(f"LOWER(COALESCE({column}, '')) LIKE '{pfx}%'" for pfx in OWNED_BIAS_PREFIXES) + ")"


def earned_news_sql(alias: str = "a") -> str:
    """Rows that count as news coverage: analysed, not a social post, not the
    company's own publishing. Every Brand Watcher metric query uses this."""
    return (f"{alias}.analyzed = true AND NOT {social_src_sql(alias + '.news_source')}"
            f" AND NOT {owned_src_sql(alias + '.bias_source')}")


def collapse_reposts(posts: list, text_keys=('summary', 'title')) -> list:
    """Fold posts that carry the same text into one entry.

    Retweets, cross-posts and bridged mirrors of one post arrive under
    different URIs. The first entry in list order is kept (feeds are newest
    first, so the newest copy) and gets ``repost_count`` (copies in total)
    and ``reposts`` (the other URIs, up to five). Posts with no text are
    left alone.
    """
    seen: dict = {}
    out = []
    for p in posts:
        text = ''
        for k in text_keys:
            if p.get(k):
                text = p[k]
                break
        key = re.sub(r'https?://\S+|\s+', ' ', (text or '').lower()).strip()
        if len(key) < 12:
            out.append(p)
            continue
        first = seen.get(key)
        if first is None:
            seen[key] = p
            out.append(p)
        else:
            first['repost_count'] = first.get('repost_count', 1) + 1
            first.setdefault('reposts', [])
            if len(first['reposts']) < 5:
                first['reposts'].append(p.get('uri'))
    return out


def classify_source(news_source: Optional[str],
                    bias_source: Optional[str] = None) -> tuple:
    """Return ``(platform, channel)`` for one article row.

    ``platform`` is None for anything that is not a social network. ``channel``
    is always one of the values ``bw_entity_content_links.channel`` allows, so
    the caller never has to invent one.
    """
    bias = (bias_source or '').strip().lower()
    if bias in OWNED_BIAS_SOURCES:
        return OWNED_BIAS_SOURCES[bias]
    if bias.startswith('owned:'):
        return None, 'owned_web'

    source = (news_source or '').strip().lower()
    if not source:
        return None, 'earned_news'
    if source in _EXACT:
        return _EXACT[source]
    if source.startswith('xpoz:'):
        platform = source.split(':', 1)[1] or 'unknown'
        return platform, _XPOZ_CHANNEL.get(platform, 'public_social')
    if source.startswith('bsky'):
        return 'bluesky', 'public_social'
    if 'glassdoor' in source:
        return 'glassdoor', 'employee'
    return None, 'earned_news'


def is_social_row(news_source: Optional[str],
                  bias_source: Optional[str] = None) -> bool:
    """Whether the row is a social post, by classification rather than substring."""
    platform, _ = classify_source(news_source, bias_source)
    return platform is not None
