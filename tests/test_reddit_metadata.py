"""Reddit posts keep the metadata the product needs: author, permalink,
timestamp and subreddit in social_meta, and engagement only when the provider
gave it. Nothing is invented for a missing field."""
import time

from app.collectors.reddit_collector import RedditCollector

# Shape of a feedparser entry from https://www.reddit.com/r/Dentistry/new/.rss
ENTRY = {
    "title": "Colgate Total vs Sensodyne for sensitive teeth?",
    "link": "https://www.reddit.com/r/Dentistry/comments/1nw4abc/colgate_total_vs_sensodyne/",
    "id": "t3_1nw4abc",
    "author": "/u/flossdaily",
    "summary": "<div>Dentist told me to switch. Anyone compared them?</div>",
    "published_parsed": time.gmtime(1759600000),
}


def test_rss_post_carries_author_permalink_timestamp_and_subreddit():
    item = RedditCollector._item(ENTRY, "Brand Monitoring Colgate", route="rss", inferred=False)
    meta = item["social_meta"]
    assert meta["platform"] == "reddit"
    assert meta["external_id"] == "t3_1nw4abc"
    assert meta["author"] == "/u/flossdaily"
    assert meta["subreddit"] == "Dentistry"
    assert meta["permalink"] == ENTRY["link"]
    assert meta["created_at"] == item["published_date"]
    assert item["published_date"].startswith("2025") or item["published_date"].startswith("2026")


def test_rss_post_does_not_invent_engagement_or_a_date():
    entry = {k: v for k, v in ENTRY.items() if k not in ("published_parsed", "author")}
    item = RedditCollector._item(entry, None, route="rss", inferred=True)
    meta = item["social_meta"]
    assert "score" not in meta and "num_comments" not in meta
    assert meta.get("author") is None
    assert "created_at" not in meta
    assert item["authors"] == []
