"""Refresh engagement metrics for recent on-brand social posts.

Collectors snapshot likes/reposts/comments at collection time — minutes after a
post is published, when everything reads 0 — and never look again, so "reach"
in Brand Watcher mostly measured how fast we found the post. This job re-polls
metrics for on-brand social posts between 6 hours and 7 days old, at most once
per ~12h per post:

  - twitter / tiktok / instagram: xpoz ``get_posts_by_ids`` (batched)
  - reddit: xpoz ``get_post_with_comments`` (per post, capped hardest)
  - bluesky: public AppView ``getPosts`` (batched, unauthenticated)

Posts whose ``social_meta`` was lost (create_article used to drop it) get it
rebuilt with platform/external_id derived from the URL where possible, so this
job also repairs that gap for recent posts.

Sync by design — call it off-loop via ``asyncio.to_thread``.
"""
import os
import re
import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

_BSKY_APPVIEW = "https://public.api.bsky.app/xrpc"
_XPOZ_BATCH = 50          # get_posts_by_ids batch size (twitter/tiktok/instagram)
_BSKY_BATCH = 25          # getPosts URI cap per request
_REDDIT_CAP = 25          # per-post calls; the most expensive path, cap hardest
_REFRESH_MIN_AGE_H = 6    # younger posts: metrics still forming, let them ripen
_REFRESH_MAX_AGE_D = 7    # older posts: reach is settled, stop polling
_REFRESH_EVERY_H = 12     # per-post refresh budget: ~2 polls/day

_URL_ID_PATTERNS = {
    "twitter": re.compile(r"/status/(\d+)"),
    "reddit": re.compile(r"/comments/([a-z0-9]+)", re.I),
    "tiktok": re.compile(r"/video/(\d+)"),
}
_BSKY_URL = re.compile(r"bsky\.app/profile/([^/]+)/post/([^/?#]+)")


def _platform_of(news_source: str, meta: Dict) -> Optional[str]:
    if meta.get("platform"):
        return meta["platform"]
    s = (news_source or "").lower()
    if s.startswith("xpoz:"):
        return s.split(":", 1)[1] or None
    if "bsky" in s or "bluesky" in s:
        return "bluesky"
    if "reddit" in s:
        return "reddit"
    return None


def _external_id_of(platform: str, uri: str, meta: Dict) -> Optional[str]:
    if meta.get("external_id"):
        return str(meta["external_id"])
    pat = _URL_ID_PATTERNS.get(platform)
    if pat:
        m = pat.search(uri or "")
        return m.group(1) if m else None
    return None


def _num(v) -> Optional[int]:
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def _as_dict(v) -> Dict:
    """social_meta defensively: JSONB usually arrives as dict, but stray rows
    hold arrays or double-encoded strings — treat anything non-dict as empty."""
    if isinstance(v, dict):
        return v
    if isinstance(v, (str, bytes)):
        try:
            obj = json.loads(v)
            return obj if isinstance(obj, dict) else {}
        except Exception:
            return {}
    return {}


class _BskyClient:
    """Minimal unauthenticated Bluesky AppView client with a handle->DID cache."""

    def __init__(self):
        import httpx
        self._http = httpx.Client(timeout=20)
        self._did_cache: Dict[str, Optional[str]] = {}

    def close(self):
        try:
            self._http.close()
        except Exception:
            pass

    def _did(self, handle: str) -> Optional[str]:
        if handle in self._did_cache:
            return self._did_cache[handle]
        did: Optional[str] = None
        try:
            if handle.startswith("did:"):
                did = handle
            else:
                r = self._http.get(f"{_BSKY_APPVIEW}/com.atproto.identity.resolveHandle",
                                   params={"handle": handle})
                if r.status_code == 200:
                    did = r.json().get("did")
        except Exception as e:
            logger.debug(f"bsky resolveHandle failed for {handle}: {e}")
        self._did_cache[handle] = did
        return did

    def metrics_for(self, urls: List[str]) -> Dict[str, Dict]:
        """Map post URL -> engagement patch for a batch of bsky.app URLs."""
        at_by_url: Dict[str, str] = {}
        for u in urls:
            m = _BSKY_URL.search(u or "")
            if not m:
                continue
            did = self._did(m.group(1))
            if did:
                at_by_url[u] = f"at://{did}/app.bsky.feed.post/{m.group(2)}"
        out: Dict[str, Dict] = {}
        items = list(at_by_url.items())
        for i in range(0, len(items), _BSKY_BATCH):
            chunk = items[i:i + _BSKY_BATCH]
            try:
                r = self._http.get(f"{_BSKY_APPVIEW}/app.bsky.feed.getPosts",
                                   params=[("uris", at_uri) for _, at_uri in chunk])
                if r.status_code != 200:
                    logger.debug(f"bsky getPosts HTTP {r.status_code}")
                    continue
                posts = {p.get("uri"): p for p in r.json().get("posts", [])}
                for url, at_uri in chunk:
                    p = posts.get(at_uri)
                    if not p:
                        continue
                    out[url] = {
                        "likes": p.get("likeCount", 0),
                        "reposts": (p.get("repostCount", 0) or 0) + (p.get("quoteCount", 0) or 0),
                        "comments": p.get("replyCount", 0),
                        "author": ((p.get("author") or {}).get("handle")),
                    }
            except Exception as e:
                logger.debug(f"bsky getPosts batch failed: {e}")
        return out


def _xpoz_metrics(client, platform: str, ids: List[str]) -> Dict[str, Dict]:
    """Map external_id -> engagement patch via xpoz, per platform."""
    out: Dict[str, Dict] = {}
    if platform == "reddit":
        for pid in ids[:_REDDIT_CAP]:
            try:
                res = client.reddit.get_post_with_comments(
                    pid, post_fields=["id", "score", "comments_count", "author_username"],
                    comment_fields=["id"])
                p = getattr(res, "post", res)
                out[str(pid)] = {
                    "likes": _num(getattr(p, "score", None)) or 0,
                    "comments": _num(getattr(p, "comments_count", None)) or 0,
                    "author": getattr(p, "author_username", None),
                }
            except Exception as e:
                logger.debug(f"xpoz reddit refresh failed for {pid}: {e}")
        return out

    ns = getattr(client, platform, None)
    if ns is None or not hasattr(ns, "get_posts_by_ids"):
        return out
    fields = {
        "twitter": ["id", "like_count", "retweet_count", "reply_count", "author_username"],
        "tiktok": ["id", "like_count", "comment_count", "play_count", "username"],
        "instagram": ["id", "like_count", "comment_count", "username"],
    }.get(platform, ["id"])
    for i in range(0, len(ids), _XPOZ_BATCH):
        chunk = ids[i:i + _XPOZ_BATCH]
        try:
            posts = ns.get_posts_by_ids(chunk, fields=fields)
        except Exception as e:
            logger.debug(f"xpoz {platform} get_posts_by_ids failed: {e}")
            continue
        for p in posts or []:
            pid = str(getattr(p, "id", "") or "")
            if not pid:
                continue
            if platform == "twitter":
                out[pid] = {"likes": _num(getattr(p, "like_count", None)) or 0,
                            "reposts": _num(getattr(p, "retweet_count", None)) or 0,
                            "comments": _num(getattr(p, "reply_count", None)) or 0,
                            "author": getattr(p, "author_username", None)}
            elif platform == "tiktok":
                out[pid] = {"likes": _num(getattr(p, "like_count", None)) or 0,
                            "comments": _num(getattr(p, "comment_count", None)) or 0,
                            "plays": _num(getattr(p, "play_count", None)) or 0,
                            "author": getattr(p, "username", None)}
            else:  # instagram
                out[pid] = {"likes": _num(getattr(p, "like_count", None)) or 0,
                            "comments": _num(getattr(p, "comment_count", None)) or 0,
                            "author": getattr(p, "username", None)}
    return out


def refresh_social_engagement(db, limit: int = 300) -> Dict:
    """Refresh engagement for on-brand social posts; returns counters."""
    from sqlalchemy import text

    now = datetime.now(timezone.utc)
    win_new = (now - timedelta(hours=_REFRESH_MIN_AGE_H)).strftime("%Y-%m-%dT%H:%M:%S")
    win_old = (now - timedelta(days=_REFRESH_MAX_AGE_D)).strftime("%Y-%m-%dT%H:%M:%S")
    stale = (now - timedelta(hours=_REFRESH_EVERY_H)).strftime("%Y-%m-%dT%H:%M:%S")

    rows = db.facade._execute_with_rollback(text("""
        SELECT uri, news_source, social_meta
        FROM articles
        WHERE (news_source LIKE 'xpoz:%' OR news_source = 'bluesky' OR news_source ILIKE '%reddit%')
          AND topic LIKE 'Brand Monitoring %'
          AND topic_alignment_score >= 0.4
          AND publication_date >= :old AND publication_date <= :new
          AND (social_meta->>'eng_refreshed_at' IS NULL OR social_meta->>'eng_refreshed_at' < :stale)
        ORDER BY publication_date DESC
        LIMIT :lim
    """), {"old": win_old, "new": win_new, "stale": stale, "lim": limit}).fetchall()
    if not rows:
        return {"candidates": 0, "refreshed": 0}

    # Group by platform, resolving ids from social_meta or the post URL.
    by_platform: Dict[str, List[Tuple[str, str, Dict]]] = {}  # platform -> [(uri, ext_id, meta)]
    bsky_urls: List[Tuple[str, Dict]] = []
    skipped = 0
    for uri, news_source, meta in rows:
        meta = _as_dict(meta)
        platform = _platform_of(news_source, meta)
        if platform == "bluesky":
            bsky_urls.append((uri, meta))
            continue
        ext = _external_id_of(platform or "", uri, meta) if platform else None
        if not platform or not ext:
            skipped += 1
            continue
        by_platform.setdefault(platform, []).append((uri, ext, meta))

    patches: Dict[str, Dict] = {}  # uri -> social_meta patch

    import time as _time
    api_key = os.getenv("XPOZ_API_KEY") or os.getenv("PROVIDER_XPOZ_API_KEY")
    if api_key and by_platform:
        try:
            from xpoz import XpozClient
            client = XpozClient(api_key, check_update=False, timeout=60)
            try:
                for platform, entries in by_platform.items():
                    t0 = _time.monotonic()
                    metrics = _xpoz_metrics(client, platform, [e[1] for e in entries])
                    logger.info(f"Engagement refresh: xpoz {platform} {len(metrics)}/{len(entries)} in {_time.monotonic()-t0:.1f}s")
                    for uri, ext, meta in entries:
                        m = metrics.get(str(ext))
                        if m is not None:
                            patches[uri] = {**m, "platform": platform, "external_id": str(ext)}
            finally:
                client.close()
        except Exception as e:
            logger.warning(f"xpoz engagement refresh failed: {e}")

    if bsky_urls:
        bsky = _BskyClient()
        try:
            t0 = _time.monotonic()
            metrics = bsky.metrics_for([u for u, _ in bsky_urls])
            logger.info(f"Engagement refresh: bluesky {len(metrics)}/{len(bsky_urls)} in {_time.monotonic()-t0:.1f}s")
            for uri, meta in bsky_urls:
                m = metrics.get(uri)
                if m is not None:
                    patches[uri] = {**m, "platform": "bluesky"}
        finally:
            bsky.close()

    stamp = now.strftime("%Y-%m-%dT%H:%M:%S")
    refreshed = 0
    meta_by_uri = {r[0]: _as_dict(r[2]) for r in rows}
    for uri, patch in patches.items():
        existing = meta_by_uri.get(uri) or {}
        # never blank an author we already have; only fill it in
        if not patch.get("author") or existing.get("author"):
            patch.pop("author", None)
        patch["eng_refreshed_at"] = stamp
        db.facade._execute_with_rollback(text(
            "UPDATE articles SET social_meta = CASE WHEN jsonb_typeof(social_meta) = 'object'"
            " THEN social_meta || CAST(:p AS jsonb) ELSE CAST(:p AS jsonb) END WHERE uri = :u"
        ), {"p": json.dumps(patch), "u": uri})
        refreshed += 1
    # Stamp the misses too, so unreachable posts (deleted, private, unresolvable)
    # don't hog the candidate window every cycle.
    for uri, *_ in rows:
        if uri not in patches:
            db.facade._execute_with_rollback(text(
                "UPDATE articles SET social_meta = CASE WHEN jsonb_typeof(social_meta) = 'object'"
            " THEN social_meta || CAST(:p AS jsonb) ELSE CAST(:p AS jsonb) END WHERE uri = :u"
            ), {"p": json.dumps({"eng_refreshed_at": stamp}), "u": uri})
    db.facade.connection.commit()

    stats = {"candidates": len(rows), "refreshed": refreshed,
             "skipped_no_id": skipped,
             "platforms": {p: len(v) for p, v in by_platform.items()} | ({"bluesky": len(bsky_urls)} if bsky_urls else {})}
    logger.info(f"Engagement refresh: {stats}")
    return stats
