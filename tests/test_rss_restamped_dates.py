"""Feed dates: read in the right timezone, and not trusted when a site has
just re-stamped its archive.

Two defects, both found on the SOC Automation market on 2026-08-27. The
collector converted feedparser's UTC struct with ``mktime``, which reads it
as local time, so every stored feed date was an hour or two early. And
Prophet Security's blog feed dated twelve old posts within one minute of
14 August 2026 — its Series A announcement, first captured by the Wayback
Machine in July 2025, surfaced in the market report as this period's funding
event. On 2026-09-01 Dropzone re-stamped just two posts 68 seconds apart and
one led the front page, so a batch is now two or more entries within a
15-minute window, not four within one minute. The Wayback lookup is stubbed
here; the rule is what is under test.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone

import feedparser

from app.collectors import rss_collector as rc


def test_feed_dates_are_read_as_utc_not_local_time():
    feed = feedparser.parse(
        '<?xml version="1.0"?><rss version="2.0"><channel><title>T</title>'
        '<item><title>A</title><link>https://x.test/a</link>'
        '<pubDate>Fri, 14 Aug 2026 09:07:52 GMT</pubDate></item></channel></rss>')
    article = rc.RSSCollector()._parse_entry(feed.entries[0], feed, "t")
    assert article["published_date"] == "2026-08-14T09:07:52+00:00"


def _article(url, stamp):
    return {"url": url, "published_date": stamp, "raw_data": {}}


def test_a_batch_is_two_or_more_entries_dated_within_the_window():
    # Dropzone, 1 Sep 2026: two old posts re-stamped 68 seconds apart.
    pair = [_article("https://x.test/a", "2026-09-01T16:54:27+00:00"),
            _article("https://x.test/b", "2026-09-01T16:55:38+00:00")]
    assert len(rc.restamped_batches(pair)) == 2
    # A lone entry is never suspect.
    assert rc.restamped_batches(pair[:1]) == []
    # Forty minutes apart: two ordinary posts in one afternoon.
    apart = [_article("https://x.test/a", "2026-08-14T02:00:00+00:00"),
             _article("https://x.test/b", "2026-08-14T02:40:00+00:00")]
    assert rc.restamped_batches(apart) == []
    # Spread over a day: a busy feed, not a migration.
    spread = [_article(f"https://x.test/{i}", f"2026-08-14T{i:02d}:00:00+00:00")
              for i in range(6)]
    assert rc.restamped_batches(spread) == []
    # A migration chains: each entry within the window of the one before.
    chain = [_article(f"https://x.test/{i}", f"2026-08-14T02:{i * 10:02d}:00+00:00")
             for i in range(5)]
    assert len(rc.restamped_batches(chain)) == 5


def _run(coro):
    return asyncio.run(coro)


def test_an_earlier_first_capture_replaces_the_feed_date_and_says_so():
    batch = [_article(f"https://x.test/{i}", "2026-08-14T02:17:30+00:00")
             for i in range(4)]
    captures = {
        "https://x.test/0": datetime(2025, 7, 31, 4, 39, tzinfo=timezone.utc),
        "https://x.test/1": None,                                   # new page
        "https://x.test/2": datetime(2026, 8, 14, 12, 0, tzinfo=timezone.utc),
        "https://x.test/3": datetime(2026, 8, 13, 0, 0, tzinfo=timezone.utc),
    }

    async def lookup(url):
        return captures[url]

    fixed = _run(rc.bound_restamped_dates(batch, lookup=lookup))
    assert fixed == 1
    old, new, same_day, day_before = batch
    assert old["published_date"] == "2025-07-31T04:39:00+00:00"
    assert old["raw_data"]["feed_published_date"] == "2026-08-14T02:17:30+00:00"
    assert old["raw_data"]["date_source"] == "wayback_first_capture"
    assert old["raw_data"]["date_precision"] == "no_later_than"
    # No capture: the feed's date stands, and the record says it was checked.
    assert new["published_date"] == "2026-08-14T02:17:30+00:00"
    assert new["raw_data"]["date_source"] == "feed"
    # A capture within the tolerance is crawl lag, not proof.
    assert same_day["published_date"] == "2026-08-14T02:17:30+00:00"
    assert day_before["published_date"] == "2026-08-14T02:17:30+00:00"


def test_nothing_is_looked_up_outside_a_batch():
    calls = []

    async def lookup(url):
        calls.append(url)
        return datetime(2020, 1, 1, tzinfo=timezone.utc)

    lone = [_article("https://x.test/a", "2026-08-14T02:17:30+00:00"),
            _article("https://x.test/b", "2026-08-15T02:17:30+00:00")]
    assert _run(rc.bound_restamped_dates(lone, lookup=lookup)) == 0
    assert calls == []
    assert lone[0]["published_date"] == "2026-08-14T02:17:30+00:00"


def test_the_wayback_key_drops_scheme_and_fragment():
    assert rc._wayback_key("https://www.Example.com/blog/post#top") == \
        "www.example.com/blog/post"
    assert rc._wayback_key("http://x.test/") == "x.test/"
