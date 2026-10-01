"""Bluesky collector.

``collect`` sends the collection interval to ``app.bsky.feed.searchPosts``
as ``since`` and ``until``, sorts by ``latest``, and pages with the API
cursor until the interval is covered or the page budget is spent (work
package 25). Before this the collector accepted a ``start_date`` and never
sent it, so a monitoring run returned posts from 2023.

Dates (work package 7): ``published_date`` is the post record's
``createdAt`` with provenance ``provider``; ``indexedAt`` is kept separately
as ``source_indexed_at``. A record without ``createdAt`` has no publication
date; nothing substitutes the indexing time or the current time.

API facts this file relies on (AT Protocol lexicon
``app.bsky.feed.searchPosts``, checked 2026-10-01): ``q``, ``sort``
(``top`` or ``latest``), ``since`` and ``until`` (ISO 8601 datetimes, or a
``YYYY-MM-DD`` date; applied to the post's ``sortAt``, which may differ from
``createdAt``), ``limit`` 1 to 100, ``cursor``; the response carries
``posts`` and an optional ``cursor``.

Spec: docs/COLLECTOR_DATA_QUALITY_SPEC.md, work packages 7 and 25.
"""
from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime
from typing import Any, Dict, List, Optional

from atproto import Client
from atproto.exceptions import AtProtocolError

from app.collectors.base_collector import (
    ArticleCollector, CONTENT_SOCIAL_POST, PageClock, coerce_datetime, in_interval,
    page_budget, provider_max_pages,
)
from app.collectors.contracts import CollectionResult
from app.collectors.dates import PROV_INDEXED, PROV_PROVIDER, parse_date

logger = logging.getLogger(__name__)


def _image_url(did: str, image) -> Optional[str]:
    """A usable CDN URL for an embedded Bluesky image.

    The API gives a blob reference, not a link. Stored as-is it is a content
    hash nothing can render, which is why the collector's existing image list
    has never been displayable. The CDN builds a URL from the author's DID and
    that hash.
    """
    try:
        ref = getattr(getattr(image, "image", None), "ref", None)
        cid = getattr(ref, "link", None) or (str(ref) if ref else None)
    except Exception:  # noqa: BLE001 — a missing thumbnail is not an error
        return None
    if not cid or not did:
        return None
    return (f"https://cdn.bsky.app/img/feed_thumbnail/plain/{did}/{cid}@jpeg")


def _post_title(handle: str, text: str) -> str:
    """A title that says what the post is about, not just who wrote it.

    Every Bluesky post used to be titled "Post by @handle", which makes a list
    of them unreadable — the reader sees twenty rows of handles and has to open
    each one. The post's own first line is the headline it would have had if
    anyone had written one, so lead with that and keep the handle as the
    attribution it is.
    """
    body = " ".join((text or "").split())
    if not body:
        return f"Post by @{handle}"
    # Cut at a sentence end when there is one early enough to be a headline,
    # otherwise at a word boundary.
    cut = body[:150]
    for stop in (". ", "! ", "? "):
        idx = cut.find(stop)
        if 30 <= idx <= 140:
            cut = cut[:idx]
            break
    else:
        if len(body) > 150:
            space = cut.rfind(" ")
            cut = (cut[:space] if space > 60 else cut) + "…"
    return f"@{handle}: {cut}".strip()


def serialize_bluesky_data(obj: Any) -> Any:
    """
    Custom serializer to handle Bluesky specific data types like IpldLink.
    Converts objects to serializable types for JSON.
    """
    if hasattr(obj, 'to_dict'):
        # Convert any object with to_dict method
        return obj.to_dict()
    elif hasattr(obj, '__dict__'):
        # Convert any object with __dict__ attribute
        return obj.__dict__
    elif hasattr(obj, 'cid') and hasattr(obj, 'json'):
        # Handle IPLD Link objects which have cid and json methods
        return str(obj.cid)
    elif isinstance(obj, (list, tuple)):
        # Handle lists/tuples
        return [serialize_bluesky_data(item) for item in obj]
    elif isinstance(obj, dict):
        # Handle dictionaries
        return {k: serialize_bluesky_data(v) for k, v in obj.items()}
    else:
        # Return primitive types as is
        return obj


def _iso_z(value: Optional[datetime]) -> Optional[str]:
    dt = coerce_datetime(value)
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ") if dt else None


class BlueskyCollector(ArticleCollector):
    """Collector for Bluesky social network posts."""

    provider_name = "bluesky"

    def __init__(self):
        self.username = os.getenv('PROVIDER_BLUESKY_USERNAME')
        self.password = os.getenv('PROVIDER_BLUESKY_PASSWORD')
        if not self.username or not self.password:
            logger.error("Bluesky credentials not found in environment")
            raise ValueError("Bluesky credentials not configured")

        self.client = Client()
        self.requests_today = 0  # rate-counter expected by keyword_monitor logging
        self._auth()

    def _auth(self):
        """Authenticate with Bluesky."""
        try:
            self.client.login(self.username, self.password)
            logger.info(
                f"Successfully authenticated to Bluesky as {self.username}"
            )
        except Exception as e:
            logger.error(f"Failed to authenticate to Bluesky: {str(e)}")
            raise ValueError(f"Bluesky authentication failed: {str(e)}")

    # -- the one API call ------------------------------------------------------

    def search_posts(self, query: str, *, limit: int = 25, since: Optional[str] = None,
                     until: Optional[str] = None, cursor: Optional[str] = None,
                     sort: Optional[str] = None, followers_of: Optional[str] = None):
        """One ``searchPosts`` call. ``since`` and ``until`` are ISO 8601
        strings. Returns the SDK response (``posts``, ``cursor``)."""
        params: Dict[str, Any] = {"q": query, "limit": max(1, min(int(limit or 25), 100))}
        if sort:
            params["sort"] = sort
        if since:
            params["since"] = since
        if until:
            params["until"] = until
        if cursor:
            params["cursor"] = cursor
        if followers_of:
            params["followersOf"] = followers_of
        logger.debug(f"Searching Bluesky with params: {params}")
        self.requests_today += 1
        return self.client.app.bsky.feed.search_posts(params=params)

    # -- mapping ---------------------------------------------------------------

    def _map_post(self, post, topic: Optional[str]) -> Dict[str, Any]:
        record = getattr(post, "record", None)
        text = getattr(record, "text", "") if record is not None else ""
        text = text or ""
        handle = post.author.handle
        created = parse_date(getattr(record, "created_at", None) if record is not None else None,
                             provenance=PROV_PROVIDER)
        indexed = parse_date(getattr(post, "indexed_at", None), provenance=PROV_INDEXED)
        article = {
            'title': _post_title(handle, text),
            'summary': text,
            'content': text,
            'content_kind': CONTENT_SOCIAL_POST,
            'authors': [post.author.display_name or handle],
            'published_date': created.iso(),
            'published_at_raw': created.raw,
            'date_provenance': created.provenance if created.known else None,
            'source_indexed_at': indexed.iso(),
            'url': (
                f"https://bsky.app/profile/{handle}/"
                f"post/{str(post.uri).split('/')[-1]}"
            ),
            'source': 'bluesky',
            'topic': topic,
            # social_meta is what the ingest pipeline actually keeps.
            'social_meta': {
                'platform': 'bluesky',
                'external_id': str(post.uri),
                'author': handle,
                'author_name': post.author.display_name or None,
                'author_did': post.author.did,
                'likes': getattr(post, 'like_count', 0),
                'reposts': getattr(post, 'repost_count', 0),
                'comments': getattr(post, 'reply_count', 0),
            },
            'raw_data': {
                'uri': str(post.uri),
                'cid': str(post.cid),
                'author_did': post.author.did,
                'author_handle': handle,
                'created_at': created.raw,
                'indexed_at': indexed.raw,
                'images': [],
                'likes': getattr(post, 'like_count', 0),
                'reposts': getattr(post, 'repost_count', 0),
            }
        }
        embed = getattr(record, 'embed', None) if record is not None else None
        if embed is not None and hasattr(embed, 'images'):
            images = embed.images or []
            article['raw_data']['images'] = [
                {
                    'alt': img.alt if hasattr(img, 'alt') else '',
                    'url': str(img.image.ref) if hasattr(getattr(img, 'image', None), 'ref') else ''
                }
                for img in images
            ]
            thumb = _image_url(post.author.did, images[0]) if images else None
            if thumb:
                article['social_meta']['thumbnail'] = thumb
        return article

    # -- structured collection ------------------------------------------------

    async def collect(
        self,
        query: str,
        topic: Optional[str] = None,
        *,
        interval_start: Optional[datetime] = None,
        interval_end: Optional[datetime] = None,
        max_results: int = 10,
        continuation: Optional[Dict[str, Any]] = None,
        sort_by: Optional[str] = None,
        limit_to_followed: bool = False,
        max_pages: Optional[int] = None,
        **kw: Any,
    ) -> CollectionResult:
        res = self.new_result(query, interval_start, interval_end)
        if not (query or "").strip():
            res.diagnostics["note"] = "empty query; no request sent"
            return self.finish(res)
        limit = max(1, min(int(max_results or 10), 100))
        since = _iso_z(res.interval_start)
        until = _iso_z(res.interval_end)
        sort = "latest"
        if sort_by and sort_by.lower() in ("top", "trending", "relevant", "relevancy"):
            sort = "top"
        cursor = (continuation or {}).get("cursor")
        res.diagnostics.update({"since": since, "until": until, "sort": sort, "limit": limit})
        pages, seconds = page_budget()
        clock = PageClock(max_pages or provider_max_pages("BLUESKY_MAX_PAGES", pages), seconds)
        seen = set()

        def _carry(out: CollectionResult, cont: Optional[Dict[str, Any]]) -> CollectionResult:
            out.items, out.counts, out.started_at = res.items, res.counts, res.started_at
            out.continuation = cont
            out.diagnostics.update(res.diagnostics)
            return self.finish(out, query, interval_start, interval_end)

        try:
            if not hasattr(self.client, 'me') or not self.client.me:
                self._auth()
            followers_of = self.client.me.did if limit_to_followed else None
            while True:
                response = await asyncio.to_thread(
                    self.search_posts, query, limit=limit, since=since, until=until,
                    cursor=cursor, sort=sort, followers_of=followers_of)
                clock.tick()
                posts = list(getattr(response, "posts", None) or [])
                res.counts.received += len(posts)
                oldest: Optional[datetime] = None
                for post in posts:
                    try:
                        item = self._map_post(post, topic)
                    except Exception as exc:  # noqa: BLE001
                        logger.error(f"Error processing Bluesky post: {exc}")
                        res.counts.invalid += 1
                        continue
                    when = coerce_datetime(item['published_date'])
                    if when and (oldest is None or when < oldest):
                        oldest = when
                    if when is not None and not in_interval(when, res.interval_start, res.interval_end):
                        res.counts.filtered += 1
                        continue
                    key = item['social_meta']['external_id']
                    if key in seen:
                        res.counts.duplicate += 1
                        continue
                    seen.add(key)
                    res.items.append(item)
                next_cursor = getattr(response, "cursor", None)
                if not next_cursor or len(posts) < limit:
                    return self.finish(res)
                if sort == "latest" and res.interval_start and oldest is not None and oldest < res.interval_start:
                    res.diagnostics["stopped_at"] = "page older than interval start"
                    return self.finish(res)
                cursor = str(next_cursor)
                if clock.exhausted:
                    out = CollectionResult.partial(res.items, truncated_reason=clock.reason,
                                                   continuation={"cursor": cursor})
                    return _carry(out, {"cursor": cursor})
        except Exception as exc:  # noqa: BLE001
            if isinstance(exc, AtProtocolError):
                logger.error(f"Bluesky API error: {type(exc).__name__}: {exc}")
            else:
                logger.error(f"Error searching Bluesky: {type(exc).__name__}: {exc}")
            out = CollectionResult.from_exception(exc, host="bsky.social")
            return _carry(out, {"cursor": cursor} if cursor else None)

    # -- compatibility list API --------------------------------------------

    async def search_articles(
        self,
        query: str,
        topic: str,
        max_results: int = 10,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        language: str = None,
        sort_by: str = None,
        limit_to_followed: bool = False,
        search_fields: Optional[List[str]] = None,
        domains: Optional[List[str]] = None,
        exclude_domains: Optional[List[str]] = None,
        **kwargs
    ) -> List[Dict]:
        """One page, as a list. Failures log and return an empty list."""
        result = await self.collect(query, topic, interval_start=start_date, interval_end=end_date,
                                    max_results=max_results, sort_by=sort_by,
                                    limit_to_followed=limit_to_followed, max_pages=1)
        if result.failed:
            logger.error(f"Bluesky search failed: {result.error_message}")
        return result.items[:max_results]

    async def fetch_article_content(self, url: str) -> Optional[Dict]:
        """
        Fetch full content of a Bluesky post.

        Args:
            url: Bluesky post URL

        Returns:
            Dictionary containing post content and metadata
        """
        try:
            # URL format:
            # https://bsky.app/profile/username.bsky.social/post/3kl5gveb2pa2r
            parts = url.split('/')
            if len(parts) < 6:
                logger.error(f"Invalid Bluesky URL format: {url}")
                return None

            handle = parts[-3]
            post_id = parts[-1]

            try:
                did_response = self.client.com.atproto.identity.resolve_handle(
                    params={"handle": handle}
                )
                did = did_response.did
            except Exception as e:
                logger.error(
                    f"Could not resolve DID for handle {handle}: {str(e)}"
                )
                return None

            post_uri = f"at://{did}/app.bsky.feed.post/{post_id}"
            thread = self.client.app.bsky.feed.get_post_thread(
                params={"uri": post_uri}
            )

            if (not thread or not hasattr(thread, 'thread') or
                    not hasattr(thread.thread, 'post')):
                logger.error(f"Could not fetch post: {url}")
                return None

            post = thread.thread.post
            item = self._map_post(post, None)
            # A thread fetched for context is an observation of the parent
            # post; the replies' dates are not a new collection.
            item['url'] = url
            item['raw_data']['thread'] = [
                {
                    'text': reply.post.record.text if hasattr(reply.post.record, 'text') else "",
                    'author': reply.post.author.handle,
                    'indexed_at': reply.post.indexed_at
                }
                for reply in thread.thread.replies
                if hasattr(reply, 'post')
            ] if hasattr(thread.thread, 'replies') and thread.thread.replies else []
            return item

        except Exception as e:
            logger.error(f"Error fetching Bluesky post content: {str(e)}")
            return None
