"""Reddit collector — subreddit feed + keyword search via Reddit's free RSS.

No OAuth / API key required. Two modes (ported from the saasmvp social collector):
1. Subreddit feed ``r/<slug>/.rss`` — the brand's own community; posts are trusted
   as relevant even when the title omits the brand name, so they bypass the term
   filter.
2. Search ``search.rss?q=<term>`` — Reddit search stems and returns cross-sub
   noise, so results are kept only when a brand term actually appears.

Datacenter IPs can be throttled (403/429) — best-effort. Built for the social
brand-monitoring path (high volume, cheap downstream eval).
"""
import os
import re
import logging
import aiohttp
import feedparser
from typing import Dict, List, Optional
from datetime import datetime, timezone
from urllib.parse import urlparse
from .base_collector import ArticleCollector

logger = logging.getLogger(__name__)

_TAG = re.compile(r"<[^>]+>")
_DEFAULT_UA = "aunoo-reddit-collector/1.0 (+https://aunoo.ai)"


def _strip_html(html: Optional[str]) -> Optional[str]:
    if not html:
        return None
    text = re.sub(r"\s+", " ", _TAG.sub(" ", html)).strip()
    return text[:1000] or None


def _entry_dt(entry) -> Optional[datetime]:
    parsed = entry.get("published_parsed") or entry.get("updated_parsed")
    if not parsed:
        return None
    try:
        return datetime(*parsed[:6], tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return None


class RedditCollector(ArticleCollector):
    """Collector for Reddit posts via free RSS feeds (no credentials)."""

    def __init__(self):
        self.user_agent = os.getenv("REDDIT_USER_AGENT", _DEFAULT_UA)
        self.base_url = "https://www.reddit.com"
        logger.info("RedditCollector initialized (RSS, no credentials)")

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
        """Search Reddit for posts mentioning the query term.

        Combines the eponymous subreddit feed (trusted) with a relevance search
        (term-filtered). Returns up to ``max_results`` standardized article dicts.
        """
        term = (query or "").strip()
        if not term:
            return []

        # Brand terms for the search-feed relevance filter (split on OR / commas).
        raw_terms = re.split(r"\s+OR\s+|,", term, flags=re.IGNORECASE)
        terms_l = [t.strip().strip('"').lower() for t in raw_terms if t.strip().strip('"')]
        primary = terms_l[0] if terms_l else term.lower()

        headers = {"User-Agent": self.user_agent, "Accept": "application/atom+xml, application/rss+xml, text/xml"}
        seen: set = set()
        out: List[Dict] = []

        # Normalize start_date for client-side date filtering of search results.
        cutoff = start_date
        if isinstance(cutoff, str):
            try:
                cutoff = datetime.fromisoformat(cutoff.replace("Z", "+00:00"))
            except ValueError:
                cutoff = None
        if cutoff is not None and cutoff.tzinfo is None:
            cutoff = cutoff.replace(tzinfo=timezone.utc)

        try:
            async with aiohttp.ClientSession() as session:
                # 1) Eponymous subreddit feed — trusted (no term filter, no date gate).
                slug = re.sub(r"[^a-z0-9]", "", primary.lower())
                if slug:
                    for e in await self._feed(session, f"{self.base_url}/r/{slug}/.rss", headers):
                        self._add(out, seen, e, topic, cutoff=None, terms=None)

                # 2) Relevance search — keep only entries mentioning a brand term.
                params = {"q": term, "sort": "relevance", "limit": min(max_results, 100), "type": "link"}
                for e in await self._feed(session, f"{self.base_url}/search.rss", headers, params=params):
                    self._add(out, seen, e, topic, cutoff=cutoff, terms=terms_l)

            logger.info(f"Reddit returned {len(out)} posts for query '{term[:60]}' (r/{slug} + search)")
            return out[:max_results]
        except aiohttp.ClientError as e:
            logger.error(f"Reddit network error: {type(e).__name__}: {e}")
            return []
        except Exception as e:
            logger.error(f"Reddit unexpected error: {type(e).__name__}: {e}")
            return []

    async def _feed(self, session, url, headers, params=None):
        try:
            async with session.get(url, headers=headers, params=params) as resp:
                if resp.status != 200:
                    logger.warning(f"Reddit feed {url} returned {resp.status}")
                    return []
                text = await resp.text()
                return feedparser.parse(text).entries or []
        except aiohttp.ClientError as exc:
            logger.warning(f"Reddit feed {url} failed: {exc}")
            return []

    def _add(self, out, seen, e, topic, *, cutoff, terms) -> None:
        title = e.get("title")
        if not title:
            return
        body = _strip_html(e.get("summary"))
        if terms is not None:  # search results must mention a brand term
            blob = f"{title} {body or ''}".lower()
            if not any(re.search(r"\b" + re.escape(t) + r"\b", blob) for t in terms):
                return
        pub = _entry_dt(e)
        if cutoff and pub and pub < cutoff:
            return
        url = e.get("link")
        ext = e.get("id") or url
        if not url or not ext or ext in seen:
            return
        seen.add(ext)

        source_name = ""
        if url:
            parsed = urlparse(url)
            source_name = parsed.netloc.replace("www.", "") or "reddit.com"
        # Extract subreddit from the reddit URL if present (/r/<sub>/...).
        m = re.search(r"/r/([A-Za-z0-9_]+)/", url or "")
        subreddit = m.group(1) if m else None

        out.append({
            "title": title,
            "summary": body or "",
            "content": body or "",
            "authors": [e.get("author")] if e.get("author") else [],
            "published_date": pub.isoformat() if pub else "",
            "url": url,
            "source": source_name or "reddit.com",
            "topic": topic,
            "raw_data": {
                "platform": "reddit",
                "external_id": ext,
                "subreddit": subreddit,
            },
        })

    async def fetch_article_content(self, url: str) -> Optional[Dict]:
        """Fetch a single Reddit post's content via its ``.json`` endpoint."""
        try:
            json_url = url.rstrip("/") + "/.json"
            headers = {"User-Agent": self.user_agent, "Accept": "application/json"}
            async with aiohttp.ClientSession() as session:
                async with session.get(json_url, headers=headers) as resp:
                    if resp.status != 200:
                        return None
                    data = await resp.json()
            # Reddit post JSON: [ {listing of post}, {listing of comments} ]
            post = data[0]["data"]["children"][0]["data"]
            body = post.get("selftext") or post.get("title", "")
            parsed = urlparse(url)
            return {
                "title": post.get("title", ""),
                "content": body,
                "authors": [post.get("author")] if post.get("author") else [],
                "published_date": datetime.fromtimestamp(
                    post.get("created_utc", 0), tz=timezone.utc
                ).isoformat() if post.get("created_utc") else "",
                "url": url,
                "source": parsed.netloc.replace("www.", "") or "reddit.com",
                "raw_data": {"platform": "reddit", "subreddit": post.get("subreddit")},
            }
        except Exception as e:
            logger.error(f"Reddit fetch_article_content error: {e}")
            return None
