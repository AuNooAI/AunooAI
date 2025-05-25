#!/usr/bin/env python3
"""
Test script for the Topic Map functionality.

This script tests the topic map service independently to ensure it works correctly.
"""

import sys
import os
import asyncio
import logging

# Add the app directory to the Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from app.database import Database
from app.vector_store import get_chroma_client
from app.services.topic_map_service import TopicMapService

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def test_topic_map_service():
    """Test the topic map service functionality."""
    
    print("=" * 60)
    print("Testing Topic Map Service")
    print("=" * 60)
    
    try:
        # Initialize database and vector store
        print("1. Initializing database and vector store...")
        db = Database()
        vector_store = get_chroma_client()
        
        # Initialize topic map service
        print("2. Initializing topic map service...")
        topic_map_service = TopicMapService(db, vector_store)
        
        # Test article extraction
        print("3. Testing article extraction...")
        articles = topic_map_service.extract_topics_from_articles(limit=50)
        print(f"   Found {len(articles)} articles")
        
        if len(articles) == 0:
            print("   ⚠️  No articles found. Make sure you have analyzed articles in your database.")
            return
        
        # Show sample article
        if articles:
            sample = articles[0]
            print(f"   Sample article: {sample['title'][:100]}...")
            print(f"   Topic: {sample.get('topic', 'N/A')}")
            print(f"   Category: {sample.get('category', 'N/A')}")
        
        # Test key phrase extraction
        print("4. Testing key phrase extraction...")
        if articles:
            sample_text = articles[0]['text']
            phrases = topic_map_service.extract_key_phrases(sample_text, max_phrases=10)
            print(f"   Extracted {len(phrases)} key phrases from sample article:")
            for i, phrase in enumerate(phrases[:5], 1):
                print(f"      {i}. {phrase}")
        
        # Test topic hierarchy building
        print("5. Testing topic hierarchy building...")
        
        # Use a smaller subset for testing
        test_articles = articles[:20] if len(articles) > 20 else articles
        hierarchy = topic_map_service.build_topic_hierarchy(test_articles, min_cluster_size=2)
        
        print(f"   Generated hierarchy with:")
        print(f"      - {len(hierarchy.get('nodes', []))} nodes")
        print(f"      - {len(hierarchy.get('edges', []))} edges")
        print(f"      - {len(hierarchy.get('clusters', []))} clusters")
        
        # Show sample nodes
        nodes = hierarchy.get('nodes', [])
        if nodes:
            print(f"   Sample nodes:")
            for i, node in enumerate(nodes[:3], 1):
                print(f"      {i}. {node['label']} ({node['type']}) - {node.get('article_count', 0)} articles")
        
        # Test full topic map generation
        print("6. Testing full topic map generation...")
        topic_map_data = topic_map_service.get_topic_map_data(limit=30)
        
        if "error" in topic_map_data:
            print(f"   ❌ Error: {topic_map_data['error']}")
        else:
            print(f"   ✅ Successfully generated topic map!")
            print(f"      - Nodes: {len(topic_map_data.get('nodes', []))}")
            print(f"      - Edges: {len(topic_map_data.get('edges', []))}")
            print(f"      - Statistics: {topic_map_data.get('statistics', {}).get('total_articles', 0)} articles analyzed")
        
        # Test statistics
        print("7. Testing statistics calculation...")
        stats = topic_map_service._calculate_topic_statistics(articles)
        print(f"   Total articles: {stats['total_articles']}")
        
        if stats['by_topic']:
            print(f"   Topics found: {len(stats['by_topic'])}")
            top_topics = sorted(stats['by_topic'].items(), key=lambda x: x[1], reverse=True)[:3]
            for topic, count in top_topics:
                print(f"      - {topic}: {count} articles")
        
        if stats['by_category']:
            print(f"   Categories found: {len(stats['by_category'])}")
            top_categories = sorted(stats['by_category'].items(), key=lambda x: x[1], reverse=True)[:3]
            for category, count in top_categories:
                print(f"      - {category}: {count} articles")
        
        print("\n✅ All tests completed successfully!")
        
    except Exception as e:
        print(f"\n❌ Test failed with error: {str(e)}")
        logger.error("Test failed", exc_info=True)
        return False
    
    return True


def main():
    """Main function to run the topic map tests."""
    
    print("Topic Map Service Test")
    print("This script tests the topic map functionality.")
    print()
    
    # Run the async test
    success = asyncio.run(test_topic_map_service())
    
    if success:
        print("\n🎉 Topic map service is working correctly!")
        print("\nNext steps:")
        print("1. Start your FastAPI server")
        print("2. Navigate to /topic-map in your browser")
        print("3. Generate and explore your topic map!")
    else:
        print("\n❌ Topic map service encountered issues.")
        print("Check the error messages above for troubleshooting.")
    
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main()) 