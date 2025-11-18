#!/usr/bin/env python3
"""Test what gets sent to LLM in Market Signals analysis."""

import sys
sys.path.insert(0, '/home/orochford/tenants/testbed.aunoo.ai')

from app.database import get_database_instance

def test_market_signals_llm_input():
    """Simulate what Market Signals route sends to LLM."""

    print("=" * 80)
    print("Simulating Market Signals LLM Input Preparation")
    print("=" * 80)

    db = get_database_instance()

    # Simulate the exact code from market_signals_routes.py
    topic = "Religion, Magic and Occultism"
    limit = 5  # Use small limit for testing

    print(f"\n1. Fetching articles for topic: {topic}")
    articles = db.facade.get_articles_by_topic(topic, limit=limit)
    print(f"   Found {len(articles)} articles\n")

    # This is the EXACT code from market_signals_routes.py line 81-92
    print("2. Preparing articles_text (as sent to LLM):\n")
    print("=" * 80)

    articles_text = "\n\n".join([
        f"Title: {a.get('title', 'N/A')}\n"
        f"Publication: {a.get('news_source', 'N/A')}\n"
        f"Publication Date: {a.get('publication_date', 'N/A')}\n"
        f"URL: {a.get('uri', 'N/A')}\n"
        f"Summary: {a.get('summary', 'N/A')}\n"
        f"Sentiment: {a.get('sentiment', 'N/A')}\n"
        f"Category: {a.get('category', 'N/A')}\n"
        f"Future Signal: {a.get('future_signal', 'N/A')}\n"
        f"Full Content: {a.get('raw_markdown', 'N/A')[:2000]}"  # ← Should include raw_markdown!
        for a in articles[:50]
    ])

    # Show first article's prepared text
    first_article_text = articles_text.split("\n\n")[0]
    print(first_article_text)
    print("=" * 80)

    # Check for Full Content field
    has_full_content = "Full Content:" in articles_text
    has_raw_data = any("raw_markdown" in str(a.get('raw_markdown', '')[:100]) for a in articles if a.get('raw_markdown'))

    print("\n3. Validation:\n")
    print(f"   Articles fetched: {len(articles)}")
    print(f"   Has 'Full Content:' field: {has_full_content}")

    # Check each article
    for i, article in enumerate(articles, 1):
        raw = article.get('raw_markdown')
        if raw:
            truncated = raw[:2000]
            print(f"   Article {i}: raw_markdown length = {len(raw)}, truncated to {len(truncated)} chars")
        else:
            print(f"   Article {i}: ❌ NO raw_markdown")

    print("\n" + "=" * 80)
    if has_full_content:
        print("✅ SUCCESS: Full Content field IS included in LLM input")
        print("\nThe LLM should now be able to extract quotes from article content!")
    else:
        print("❌ FAILED: Full Content field is NOT in LLM input")
        print("\nThe code changes may not have been applied correctly.")

    print("=" * 80)

if __name__ == "__main__":
    test_market_signals_llm_input()
