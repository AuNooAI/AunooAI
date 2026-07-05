"""Xpoz collector — social brand mentions across Twitter/X, Reddit, Instagram, TikTok.

Uses the xpoz.ai SDK (``pip install xpoz``) to run one keyword search per platform
and return standardized article dicts. Built for the social brand-monitoring path
(high volume, cheap downstream eval), mirroring ``reddit_collector.py``.

Auth: ``XPOZ_API_KEY`` (or ``PROVIDER_XPOZ_API_KEY``).
Platforms: ``XPOZ_PLATFORMS`` env, comma-separated (default: all four).

The SDK client is synchronous, so the whole per-search workload runs in a worker
thread via ``asyncio.to_thread`` to keep the collector's ``async`` contract.
Xpoz serves a rolling ~60-day window; older ``start_date`` values are best-effort.
"""
import os
import re
import asyncio
import logging
from typing import Dict, List, Optional
from datetime import datetime, timezone

from .base_collector import ArticleCollector

logger = logging.getLogger(__name__)

_ALL_PLATFORMS = ("twitter", "reddit", "instagram", "tiktok")

# Xpoz returns a minimal default projection, so URL/metric fields must be requested
# explicitly per platform or they come back null (and rows get dropped for lack of URL).
_FIELDS = {
    "twitter": ["id", "text", "author_username", "like_count", "retweet_count",
                "reply_count", "media_urls", "created_at", "created_at_date"],
    "reddit": ["id", "title", "selftext", "permalink", "post_url", "url",
               "thumbnail", "author_username", "subreddit_name", "score",
               "comments_count", "created_at", "created_at_date"],
    "instagram": ["id", "caption", "code_url", "image_url", "username",
                  "like_count", "comment_count", "media_type", "created_at",
                  "created_at_date"],
    "tiktok": ["id", "description", "username", "video_url", "video_thumbnail",
               "like_count", "comment_count", "play_count", "created_at",
               "created_at_date"],
}


def _api_key() -> Optional[str]:
    return os.getenv("XPOZ_API_KEY") or os.getenv("PROVIDER_XPOZ_API_KEY")


def _platforms() -> List[str]:
    raw = os.getenv("XPOZ_PLATFORMS", "")
    if not raw.strip():
        return list(_ALL_PLATFORMS)
    want = [p.strip().lower() for p in raw.split(",") if p.strip()]
    return [p for p in want if p in _ALL_PLATFORMS] or list(_ALL_PLATFORMS)


def _max_per_platform() -> int:
    """Hard cap on posts fetched per platform per keyword (cost control).

    The keyword monitor passes its global page_size (often 100), which — multiplied
    by keywords × 4 platforms × 4 brands — is a large paid-API + eval bill. Cap it
    low for brand-monitoring volume; override with XPOZ_MAX_RESULTS.
    """
    try:
        return max(1, int(os.getenv("XPOZ_MAX_RESULTS", "25")))
    except ValueError:
        return 25


def _to_date_str(value) -> Optional[str]:
    """Coerce a datetime/ISO string to the ``YYYY-MM-DD`` xpoz expects."""
    if not value:
        return None
    if isinstance(value, datetime):
        return value.date().isoformat()
    s = str(value)
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00")).date().isoformat()
    except ValueError:
        return s[:10] if len(s) >= 10 else None


def _pub_iso(post) -> str:
    """Best-effort ISO timestamp from a post's created_at / created_at_date."""
    ca = getattr(post, "created_at", None)
    if isinstance(ca, (int, float)) and ca:
        try:
            return datetime.fromtimestamp(ca, tz=timezone.utc).isoformat()
        except (OverflowError, OSError, ValueError):
            pass
    if isinstance(ca, str) and ca.strip():
        try:
            return datetime.fromisoformat(ca.replace("Z", "+00:00")).isoformat()
        except ValueError:
            return ca
    cad = getattr(post, "created_at_date", None)
    return str(cad) if cad else ""


def _clean(text: Optional[str], limit: int = 1000) -> str:
    if not text:
        return ""
    return re.sub(r"\s+", " ", str(text)).strip()[:limit]


class XpozCollector(ArticleCollector):
    """Collector for social posts via the xpoz.ai SDK (one search per platform)."""

    def __init__(self):
        self.api_key = _api_key()
        if not self.api_key:
            raise ValueError(
                "Xpoz API key not configured. Set XPOZ_API_KEY environment variable."
            )
        self.platforms = _platforms()
        self.requests_today = 0  # rate-counter expected by keyword_monitor logging
        logger.info("XpozCollector initialized (platforms=%s)", ",".join(self.platforms))

    async def search_articles(
        self,
        query: str,
        topic: str,
        max_results: int = 10,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        language: str = "en",
        locale: Optional[str] = None,
        domains: Optional[List[str]] = None,
        exclude_domains: Optional[List[str]] = None,
        sort_by: Optional[str] = None,
        source_ids: Optional[List[str]] = None,
        exclude_source_ids: Optional[List[str]] = None,
        categories: Optional[List[str]] = None,
        exclude_categories: Optional[List[str]] = None,
        search_fields: Optional[List[str]] = None,
        page: int = 1,
    ) -> List[Dict]:
        """Search each configured platform for ``query`` and return standardized dicts.

        ``max_results`` is applied per platform, so up to ``max_results * len(platforms)``
        posts may be returned per cycle — appropriate for high-volume brand monitoring.
        """
        term = (query or "").strip()
        if not term:
            return []
        per_platform = min(max(1, int(max_results or 10)), _max_per_platform())
        try:
            return await asyncio.to_thread(
                self._search_sync,
                term,
                topic,
                per_platform,
                _to_date_str(start_date),
                _to_date_str(end_date),
            )
        except Exception as e:  # noqa: BLE001 - best-effort collector
            logger.error("Xpoz search failed: %s: %s", type(e).__name__, e)
            return []

    def _search_sync(self, term, topic, per_platform, start_date, end_date) -> List[Dict]:
        from xpoz import XpozClient

        out: List[Dict] = []
        client = XpozClient(self.api_key, check_update=False)
        try:
            for plat in self.platforms:
                try:
                    ns = getattr(client, plat, None)
                    if ns is None:
                        continue
                    result = ns.search_posts(
                        term,
                        fields=_FIELDS.get(plat),
                        start_date=start_date,
                        end_date=end_date,
                        limit=per_platform,
                    )
                    posts = getattr(result, "data", None) or []
                    mapper = getattr(self, f"_map_{plat}")
                    for post in posts[:per_platform]:
                        row = mapper(post, topic)
                        if row:
                            out.append(row)
                    logger.info(
                        "Xpoz %s returned %d posts for '%s'",
                        plat, len(posts), term[:60],
                    )
                except Exception as e:  # noqa: BLE001 - one platform failing shouldn't kill the rest
                    logger.warning("Xpoz %s search error: %s: %s", plat, type(e).__name__, e)
        finally:
            try:
                client.close()
            except Exception:  # noqa: BLE001
                pass
        self.requests_today += len(self.platforms)
        return out

    # -- per-platform mappers -> standardized article dict --------------------

    def _row(self, *, title, body, author, pub, url, platform, external_id, topic, meta):
        if not url or not external_id:
            return None
        # social_meta carries what the ingest pipeline would otherwise discard:
        # normalized engagement (likes/reposts/comments/plays) + a thumbnail URL.
        social_meta = {"platform": platform, "external_id": str(external_id)}
        if author:
            social_meta["author"] = author
        for k, v in (meta or {}).items():
            if v is not None and v != "":
                social_meta[k] = v
        return {
            "title": _clean(title, 300) or (body[:120] if body else platform),
            "summary": body,
            "content": body,
            "authors": [author] if author else [],
            "published_date": pub,
            "url": url,
            "source": f"xpoz:{platform}",
            "topic": topic,
            "social_meta": social_meta,
            "raw_data": {"platform": platform, "external_id": str(external_id), "provider": "xpoz"},
        }

    def _map_twitter(self, p, topic):
        author = getattr(p, "author_username", None)
        pid = getattr(p, "id", None)
        handle = author or "i"
        url = f"https://x.com/{handle}/status/{pid}" if pid else None
        media = getattr(p, "media_urls", None)
        return self._row(
            title=getattr(p, "text", None),
            body=_clean(getattr(p, "text", None)),
            author=author,
            pub=_pub_iso(p),
            url=url,
            platform="twitter",
            external_id=pid,
            topic=topic,
            meta={
                "likes": getattr(p, "like_count", None),
                "reposts": getattr(p, "retweet_count", None),
                "comments": getattr(p, "reply_count", None),
                "thumbnail": media[0] if isinstance(media, (list, tuple)) and media else None,
            },
        )

    def _map_reddit(self, p, topic):
        permalink = getattr(p, "permalink", None)
        pid = getattr(p, "id", None)
        url = getattr(p, "post_url", None)
        if not url and permalink:
            url = permalink if permalink.startswith("http") else "https://www.reddit.com" + permalink
        if not url:
            url = getattr(p, "url", None) or (f"https://redd.it/{pid}" if pid else None)
        title = getattr(p, "title", None)
        body = _clean(getattr(p, "selftext", None)) or _clean(title)
        thumb = getattr(p, "thumbnail", None)
        if not (isinstance(thumb, str) and thumb.startswith("http")):
            thumb = None  # reddit uses 'self'/'default'/'nsfw' placeholders
        return self._row(
            title=title,
            body=body,
            author=getattr(p, "author_username", None),
            pub=_pub_iso(p),
            url=url,
            platform="reddit",
            external_id=getattr(p, "id", None),
            topic=topic,
            meta={
                "subreddit": getattr(p, "subreddit_name", None),
                "likes": getattr(p, "score", None),
                "comments": getattr(p, "comments_count", None),
                "thumbnail": thumb,
            },
        )

    def _map_instagram(self, p, topic):
        caption = _clean(getattr(p, "caption", None))
        username = getattr(p, "username", None)
        url = getattr(p, "code_url", None) or (
            f"https://www.instagram.com/{username}/" if username else None)
        return self._row(
            title=caption,
            body=caption,
            author=username,
            pub=_pub_iso(p),
            url=url,
            platform="instagram",
            external_id=getattr(p, "id", None),
            topic=topic,
            meta={
                "likes": getattr(p, "like_count", None),
                "comments": getattr(p, "comment_count", None),
                "media_type": getattr(p, "media_type", None),
                "thumbnail": getattr(p, "image_url", None),
            },
        )

    def _map_tiktok(self, p, topic):
        desc = _clean(getattr(p, "description", None))
        username = getattr(p, "username", None)
        pid = getattr(p, "id", None)
        url = getattr(p, "video_url", None)
        if not url and username and pid:
            url = f"https://www.tiktok.com/@{username}/video/{pid}"
        return self._row(
            title=desc,
            body=desc,
            author=username,
            pub=_pub_iso(p),
            url=url,
            platform="tiktok",
            external_id=pid,
            topic=topic,
            meta={
                "likes": getattr(p, "like_count", None),
                "comments": getattr(p, "comment_count", None),
                "plays": getattr(p, "play_count", None),
                "thumbnail": getattr(p, "video_thumbnail", None),
            },
        )

    async def fetch_article_content(self, url: str) -> Optional[Dict]:
        """Xpoz posts are self-contained (search returns full text) — no re-fetch."""
        return None
