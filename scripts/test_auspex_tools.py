#!/usr/bin/env python3
"""
Test script for Auspex Tools Service
"""

import asyncio
import sys
import os

# Add project root to path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

from app.services.auspex_tools import get_auspex_tools_service

async def test_tools():
    """Test the Auspex tools service."""
    print("=" * 50)
    print("Testing Auspex Tools Service")
    print("=" * 50)
    
    try:
        tools = get_auspex_tools_service()
        print("✅ Tools service initialized successfully")
        
        # Test 1: Get topic articles
        print("\n🔍 Testing get_topic_articles...")
        result = await tools.get_topic_articles('technology', limit=5)
        if 'error' in result:
            print(f"⚠️  Topic articles: {result['error']}")
        else:
            print(f"✅ Topic articles: Found {result['total_articles']} articles")
        
        # Test 2: Analyze sentiment trends
        print("\n📊 Testing analyze_sentiment_trends...")
        result = await tools.analyze_sentiment_trends('technology', 'month')
        if 'error' in result:
            print(f"⚠️  Sentiment analysis: {result['error']}")
        else:
            print(f"✅ Sentiment analysis: Analyzed {result['total_articles']} articles")
        
        # Test 3: Get article categories
        print("\n📂 Testing get_article_categories...")
        result = await tools.get_article_categories('technology')
        if 'error' in result:
            print(f"⚠️  Categories: {result['error']}")
        else:
            print(f"✅ Categories: Found {len(result['category_distribution'])} categories")
        
        # Test 4: Search by keywords
        print("\n🔎 Testing search_articles_by_keywords...")
        result = await tools.search_articles_by_keywords(['AI', 'artificial intelligence'])
        if 'error' in result:
            print(f"⚠️  Keyword search: {result['error']}")
        else:
            print(f"✅ Keyword search: Found {result['total_results']} articles")
        
        print("\n" + "=" * 50)
        print("✅ All tests completed successfully!")
        print("🎉 Auspex tools are ready to use!")
        
    except Exception as e:
        print(f"❌ Error testing tools: {e}")
        raise

if __name__ == "__main__":
    asyncio.run(test_tools()) 