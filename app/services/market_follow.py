"""Accounts we follow for a market, and their posts.

The social collector is keyword-driven: it sees a person's post only when it
contains one of the market's phrases, so a known analyst shows up with one
matched reply and nothing else. Following an account reads its recent
timeline instead and keeps the posts that touch the market — a market phrase
or a tracked vendor's name in the text. Followed posts land in ``articles``
and are attached to the market like any collected post
(``bw_market_articles.method = 'watchlist'``), so they appear in the Social
section, the river and the voices table.

The follow list is ``social_accounts.watchlisted``, shared with Brand Watcher's
Accounts view. Following an account profiles it first (two xpoz calls and one
short model call, the same profile as everywhere else) so the front page can
say who the person is.

Platforms: X through xpoz (``get_posts_by_author``) and Bluesky through its
public API. Reddit has no per-user history through xpoz, so a Reddit account
can be followed but yields nothing until that changes.
"""
import asyncio
import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import text

logger = logging.getLogger(__name__)

FOLLOW_PLATFORMS = ("twitter", "bluesky", "reddit")
FETCHABLE = ("twitter", "bluesky")
SOURCE = "watchlist_posts"
METHOD = "watchlist"
ORIGIN = "follow"
MAX_POSTS = 40
WINDOW_DAYS = 14


def followed(conn, limit: int = 100) -> List[Dict[str, Any]]:
    """The accounts on the follow list, most followed first."""
    return [dict(r) for r in conn.execute(text("""
        SELECT id, platform, handle, display_name, followers_count, profile_url,
               avatar_url, last_profiled_at,
               metadata->>'market_role' AS role
          FROM social_accounts
         WHERE watchlisted AND platform = ANY(:p)
         ORDER BY followers_count DESC NULLS LAST, handle
         LIMIT :lim
    """), {"p": list(FOLLOW_PLATFORMS), "lim": limit}).mappings().all()]


async def follow(db, platform: str, handle: str, market_name: str) -> Optional[Dict[str, Any]]:
    """Put an account on the follow list, profiling it first when it has no
    profile. None when the platform knows no such account."""
    from app.services import market_voice_profiles as mvp
    from app.services.social_profile_service import SocialProfileService

    platform = (platform or "").strip().lower()
    handle = (handle or "").strip().lstrip("@")
    if platform not in FOLLOW_PLATFORMS or not handle:
        raise ValueError("platform must be twitter, bluesky or reddit, and a handle is needed")
    svc = SocialProfileService()
    row = svc.get_stored(db, platform, handle)
    if not row or not row.get("last_profiled_at"):
        row = await mvp.profile_one(db, platform, handle, market_name)
    if not row:
        return None
    return svc.set_watchlist(db, int(row["id"]), True)


def unfollow(db, platform: str, handle: str) -> bool:
    from app.services.social_profile_service import SocialProfileService

    svc = SocialProfileService()
    row = svc.get_stored(db, (platform or "").lower(), (handle or "").lstrip("@"))
    if not row:
        return False
    svc.set_watchlist(db, int(row["id"]), False)
    return True


# ---------------------------------------------------------------------------
# Reading a followed account's timeline
# ---------------------------------------------------------------------------

def _fetch_posts(svc, platform: str, handle: str, max_posts: int) -> List[Dict[str, Any]]:
    if platform == "bluesky":
        ident = asyncio.run(svc._bluesky_fetch(handle, max_posts))
    elif platform in FETCHABLE:
        ident = svc._fetch_sync(platform, handle, max_posts)
    else:
        return []
    return list((ident or {}).get("posts") or [])


def _term_patterns(terms: List[str]) -> List[Tuple[str, re.Pattern]]:
    """Each market phrase as a whole-phrase, word-bounded pattern."""
    out = []
    for term in terms:
        words = [w for w in re.findall(r"[a-z0-9']+", (term or "").lower()) if len(w) >= 2]
        if not words:
            continue
        out.append((term, re.compile(r"(?<![a-z0-9])" + r"\W+".join(re.escape(w) for w in words)
                                     + r"(?![a-z0-9])")))
    return out


def touches_market(text_value: str, term_patterns: List[Tuple[str, re.Pattern]],
                   vendor_patterns: List[Tuple[str, re.Pattern]]) -> List[str]:
    """The market phrases and vendor names the text contains; empty when
    the post is about something else."""
    hay = (text_value or "").lower()
    hits = [t for t, p in term_patterns if p.search(hay)]
    hits += [v for v, p in vendor_patterns if p.search(hay)]
    return hits


def _published(post: Dict[str, Any]) -> Optional[datetime]:
    raw = post.get("created_at")
    if not raw:
        return None
    try:
        stamp = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    except ValueError:
        return None
    return stamp if stamp.tzinfo else stamp.replace(tzinfo=timezone.utc)


def collect_followed(conn, market: Dict[str, Any], *, days: int = WINDOW_DAYS,
                     max_posts: int = MAX_POSTS) -> Dict[str, Any]:
    """Read every followed account's recent posts and keep the ones that
    touch the market. Returns counts. Sync; call it off the loop."""
    from app.services import market_briefing as mbr
    from app.services import market_corpus as mcorp
    from app.services import market_publish as mp
    from app.services.market_collect import land_article
    from app.services.social_profile_service import SocialProfileService

    accounts = followed(conn)
    if not accounts:
        return {"accounts": 0, "fetched": 0, "matched": 0, "stored": 0, "skipped": []}
    terms = _term_patterns(list(mcorp.corpus_terms(conn, market["id"]) or []))
    vendors = [(d["vendor"], re.compile(r"(?<![a-z0-9])" + re.escape(d["vendor"].lower()) + r"(?![a-z0-9])"))
               for d in mp.build_dataset(conn, market["id"]) if d.get("vendor") and len(d["vendor"]) >= 3]
    topic = mbr.market_topic(market)
    since = datetime.now(timezone.utc) - timedelta(days=days)
    svc = SocialProfileService()
    fetched = matched = stored = 0
    skipped: List[str] = []
    for acct in accounts:
        platform, handle = acct["platform"], acct["handle"]
        if platform not in FETCHABLE:
            skipped.append(f"{platform}/{handle}: no timeline through the provider")
            continue
        try:
            posts = _fetch_posts(svc, platform, handle, max_posts)
        except Exception as exc:                                  # noqa: BLE001
            logger.warning("follow: %s/%s timeline failed: %s", platform, handle, exc)
            skipped.append(f"{platform}/{handle}: {str(exc)[:80]}")
            continue
        fetched += len(posts)
        for post in posts:
            when = _published(post)
            if not post.get("url") or not post.get("id") or (when and when < since):
                continue
            body = (post.get("text") or "").strip()
            hits = touches_market(body, terms, vendors)
            if not hits:
                continue
            matched += 1
            meta = {"platform": platform, "author": handle, "external_id": str(post["id"]),
                    "followed": True}
            for k in ("likes", "comments", "reposts", "thumbnail"):
                if post.get(k) is not None:
                    meta[k] = post[k]
            is_new = land_article(
                conn, uri=post["url"], title=f"@{handle}: {body[:200]}", summary=body[:1000],
                news_source=("bluesky" if platform == "bluesky" else f"xpoz:{platform}"),
                published_at=(when.strftime("%Y-%m-%dT%H:%M:%S.%fZ") if when else None),
                topic=topic, category="", bias_source="", social_meta=meta)
            conn.execute(text("""
                INSERT INTO bw_market_articles
                    (market_id, article_uri, matched_terms, title_terms, body_terms,
                     score, method, origin)
                VALUES (:m, :uri, :terms, 0, 1, 1.0, :method, :origin)
                ON CONFLICT (market_id, article_uri) DO NOTHING
            """), {"m": market["id"], "uri": post["url"], "terms": hits[:10],
                   "method": METHOD, "origin": ORIGIN})
            if is_new:
                stored += 1
    conn.commit()
    return {"accounts": len(accounts), "fetched": fetched, "matched": matched,
            "stored": stored, "skipped": skipped}
