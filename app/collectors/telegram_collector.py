"""Telegram collector: public channel previews, no credentials.

Telegram has no public search without an API key, so this collector is
channel-based rather than query-based. It reads the public web preview of
each configured channel (``https://t.me/s/<channel>``), which Telegram
serves as plain HTML for any channel the owner has made public, then keeps
the posts matching the caller's keyword. That is the same shape the other
collectors present: ``search_articles(query, ...)`` returns the posts in
the configured channels that match ``query``.

Matching is an AND of the query's words over the post text, the same rule
the NewsFirehose collector uses, so an anchored keyword such as
"Neutralitätsinitiative Russland" behaves the way it does elsewhere.

Channels come from the ``TELEGRAM_CHANNELS`` env var (comma-separated
channel names, no @). Nothing is hard-coded as a default: an unset
variable means the collector returns nothing rather than reading channels
nobody chose. Verify a channel before adding it — many names 404 or are
private, and this collector reads only what Telegram already publishes on
the open web.
"""
import asyncio
import html
import logging
import os
import re
from datetime import datetime, timezone
from typing import Dict, List, Optional

import httpx

from .base_collector import ArticleCollector

logger = logging.getLogger(__name__)

PREVIEW_URL = "https://t.me/s/{channel}"
USER_AGENT = "Mozilla/5.0 (compatible; AunooAI Feed Reader/1.0; +https://aunoo.ai)"
TIMEOUT = float(os.getenv("TELEGRAM_TIMEOUT", "20"))

_TEXT_RE = re.compile(r'<div class="tgme_widget_message_text[^"]*"[^>]*>(.*?)</div>', re.S)
_POST_RE = re.compile(r'data-post="([^"]+)"')
_TIME_RE = re.compile(r'<time datetime="([^"]+)"')
_VIEWS_RE = re.compile(r'tgme_widget_message_views">([^<]+)<')
_TAG_RE = re.compile(r"<[^>]+>")
_BR_RE = re.compile(r"<br\s*/?>", re.I)


def _channels() -> List[str]:
    raw = os.getenv("TELEGRAM_CHANNELS", "")
    return [c.strip().lstrip("@") for c in raw.split(",") if c.strip()]


def _clean(fragment: str) -> str:
    text = html.unescape(_TAG_RE.sub("", _BR_RE.sub(" ", fragment)))
    return " ".join(text.split())


def _title(channel: str, text: str, limit: int = 120) -> str:
    """Lead with the post's own words; a list of channel names is unreadable."""
    first = text.strip().split("\n", 1)[0].strip()
    if not first:
        return f"Telegram post from @{channel}"
    cut = first if len(first) <= limit else first[:limit].rsplit(" ", 1)[0] + "…"
    return f"@{channel}: {cut}"


def _matches(text: str, query: str) -> bool:
    """AND of the query's words, case-insensitive, same rule as the firehose."""
    words = [w for w in re.split(r"\s+", (query or "").strip()) if w]
    if not words:
        return False
    low = text.lower()
    return all(w.lower() in low for w in words)


def _views(raw: str) -> int:
    raw = (raw or "").strip().upper()
    try:
        if raw.endswith("K"):
            return int(float(raw[:-1]) * 1_000)
        if raw.endswith("M"):
            return int(float(raw[:-1]) * 1_000_000)
        return int(raw)
    except ValueError:
        return 0


class TelegramCollector(ArticleCollector):
    """Reads public Telegram channel previews. No API key, no login."""

    def __init__(self):
        self.requests_today = 0  # rate counter the keyword monitor logs
        self.channels = _channels()
        if not self.channels:
            logger.warning("TELEGRAM_CHANNELS is unset; the Telegram collector will return nothing")

    async def _fetch_channel(self, client: httpx.AsyncClient, channel: str) -> List[Dict]:
        url = PREVIEW_URL.format(channel=channel)
        try:
            resp = await client.get(url, headers={"User-Agent": USER_AGENT},
                                    follow_redirects=True, timeout=TIMEOUT)
            self.requests_today += 1
            if resp.status_code != 200:
                logger.warning("Telegram %s returned %s", channel, resp.status_code)
                return []
            body = resp.text
        except Exception as e:
            logger.warning("Telegram %s fetch failed: %s", channel, e)
            return []

        texts = _TEXT_RE.findall(body)
        posts = _POST_RE.findall(body)
        times = _TIME_RE.findall(body)
        views = _VIEWS_RE.findall(body)
        if not texts:
            logger.info("Telegram %s: preview had no message text (private or empty)", channel)
            return []

        out: List[Dict] = []
        for i, fragment in enumerate(texts):
            text = _clean(fragment)
            if not text:
                continue
            post_id = posts[i] if i < len(posts) else f"{channel}/?"
            stamp = times[i] if i < len(times) else None
            out.append({
                "channel": channel,
                "text": text,
                "post_id": post_id,
                "url": f"https://t.me/{post_id}",
                "published": stamp,
                "views": _views(views[i]) if i < len(views) else 0,
            })
        return out

    async def search_articles(
        self,
        query: str,
        topic: str,
        max_results: int = 10,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        **kwargs,
    ) -> List[Dict]:
        """Posts in the configured channels whose text matches every word of query."""
        if not self.channels:
            return []
        async with httpx.AsyncClient() as client:
            batches = await asyncio.gather(
                *[self._fetch_channel(client, c) for c in self.channels],
                return_exceptions=True)

        results: List[Dict] = []
        for batch in batches:
            if isinstance(batch, Exception):
                logger.warning("Telegram channel fetch raised: %s", batch)
                continue
            for post in batch:
                if not _matches(post["text"], query):
                    continue
                published = post["published"]
                if published and start_date:
                    try:
                        when = datetime.fromisoformat(published.replace("Z", "+00:00"))
                        floor = start_date if start_date.tzinfo else start_date.replace(tzinfo=timezone.utc)
                        if when < floor:
                            continue
                    except ValueError:
                        pass
                channel = post["channel"]
                results.append({
                    "title": _title(channel, post["text"]),
                    "summary": post["text"][:2000],
                    "content": post["text"],
                    "authors": [f"@{channel}"],
                    "published_date": published,
                    "url": post["url"],
                    "source": "telegram",
                    "topic": topic,
                    # social_meta is what the ingest pipeline reads for social
                    # posts; the handle doubles as the source domain, so
                    # sd_sources can tier a channel like any other outlet.
                    "social_meta": {
                        "platform": "telegram",
                        "external_id": post["post_id"],
                        "author": f"t.me/{channel}",
                        "author_name": channel,
                        "likes": 0,
                        "reposts": 0,
                        "comments": 0,
                        "views": post["views"],
                    },
                    "raw_data": {
                        "channel": channel,
                        "post_id": post["post_id"],
                        "views": post["views"],
                    },
                })
        results.sort(key=lambda r: r.get("published_date") or "", reverse=True)
        if results:
            logger.info("Telegram: %s posts matched %r across %s channels",
                        len(results), query, len(self.channels))
        return results[:max_results]

    async def fetch_article_content(self, url: str) -> Optional[Dict]:
        """A preview post is already its whole text; nothing further to fetch."""
        return None
