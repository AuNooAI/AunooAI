"""RSS items that link to a social post are not stored as news (6 Oct 2026:
a Bluesky post from a newsletter feed reached wileytest's news)."""
import asyncio

import pytest

from app.tasks.rss_feed_monitor import STORE_EXISTING, RSSFeedMonitor


class _Self:
    _last_store_error = None


@pytest.mark.parametrize("url", [
    "https://bsky.app/profile/atrupar.com/post/3mwbqj54jv22a?utm_source=substack",
    "https://x.com/someone/status/1",
    "https://www.reddit.com/r/science/comments/abc/",
    "https://truthsocial.com/@user/posts/1",
])
def test_social_post_links_are_skipped_before_any_store(url):
    out = asyncio.run(RSSFeedMonitor._store_article(_Self(), {"url": url, "title": "t"}, "Trend Monitoring"))
    assert out == STORE_EXISTING
