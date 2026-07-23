"""Single source of truth for "is this article row a social post?".

Social posts (Reddit / Bluesky / X / Instagram / TikTok via the xpoz API) live in
the same `articles` table as news, distinguished only by `news_source` naming
conventions: 'xpoz:<platform>', 'bluesky', 'reddit.com', 'bsky*', ...

Historically each consumer hand-rolled its own predicate and they drifted — the
worst case being the social evaluator missing 'xpoz', which left every X/
Instagram/TikTok post unscored and invisible while the alert rules (with their
own, correct predicate) could still count them. Import from here instead:

  - SOCIAL_SOURCES: substrings for parameterized LIKE filters
  - is_social_source(): python-side check
  - social_src_sql(): ready-made SQL predicate for raw queries

Adding a platform = adding one substring here.
"""
from typing import Optional

SOCIAL_SOURCES = ("reddit", "bluesky", "bsky", "xpoz")


def is_social_source(news_source: Optional[str]) -> bool:
    s = (news_source or "").lower()
    return any(k in s for k in SOCIAL_SOURCES)


def social_src_sql(column: str = "news_source") -> str:
    """SQL predicate matching social rows, e.g. social_src_sql('a.news_source').

    Values are the static SOCIAL_SOURCES constants (never user input), so
    inlining them as literals is safe and keeps call sites bind-param-free.
    """
    return "(" + " OR ".join(f"LOWER({column}) LIKE '%{k}%'" for k in SOCIAL_SOURCES) + ")"
