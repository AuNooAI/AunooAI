#!/usr/bin/env python3
"""Test script to validate raw_markdown is being fetched."""

import sys
sys.path.insert(0, '/home/orochford/tenants/testbed.aunoo.ai')

from app.database import get_database_instance

def test_raw_markdown_fetch():
    """Test if get_articles_by_topic returns raw_markdown."""

    print("=" * 80)
    print("Testing raw_markdown fetch in get_articles_by_topic()")
    print("=" * 80)

    db = get_database_instance()

    # Get articles for a topic
    topic = "Religion, Magic and Occultism"
    print(f"\nFetching articles for topic: {topic}")

    articles = db.facade.get_articles_by_topic(topic, limit=5)

    print(f"\nFound {len(articles)} articles")
    print("\nChecking raw_markdown field:\n")

    for i, article in enumerate(articles, 1):
        uri = article.get('uri', 'N/A')
        title = article.get('title', 'N/A')[:60]
        has_raw = 'raw_markdown' in article
        raw_markdown = article.get('raw_markdown')

        print(f"Article {i}:")
        print(f"  URI: {uri}")
        print(f"  Title: {title}...")
        print(f"  Has 'raw_markdown' key: {has_raw}")

        if raw_markdown is not None:
            print(f"  Raw markdown length: {len(raw_markdown)} chars")
            print(f"  First 100 chars: {raw_markdown[:100]}...")
            print(f"  ✅ SUCCESS - raw_markdown is present")
        else:
            print(f"  ❌ FAILED - raw_markdown is None or missing")

        print()

    # Summary
    with_raw = sum(1 for a in articles if a.get('raw_markdown') is not None)
    print("=" * 80)
    print(f"SUMMARY: {with_raw}/{len(articles)} articles have raw_markdown")
    print("=" * 80)

    if with_raw == 0:
        print("\n❌ PROBLEM: No articles have raw_markdown!")
        print("The LEFT JOIN may not be working correctly.")
        return False
    elif with_raw < len(articles):
        print(f"\n⚠️  WARNING: Only {with_raw}/{len(articles)} articles have raw_markdown")
        print("Some articles may not have been scraped for full content.")
        return True
    else:
        print("\n✅ SUCCESS: All articles have raw_markdown!")
        return True

if __name__ == "__main__":
    success = test_raw_markdown_fetch()
    sys.exit(0 if success else 1)
