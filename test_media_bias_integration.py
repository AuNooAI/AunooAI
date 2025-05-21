#!/usr/bin/env python3
"""Test script to verify media bias integration with articles."""

import sys
import os
import logging
import asyncio
from urllib.parse import urlparse

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Add app directory to path
sys.path.insert(0, os.path.abspath('.'))

from app.database import get_database_instance
from app.models.media_bias import MediaBias, normalize_domain
from app.research import Research


async def test_save_article_with_bias():
    """Test saving articles with media bias data."""
    print("\n=== Testing Article Save with Media Bias ===")
    
    # Get database connection
    db = get_database_instance()
    
    # Create MediaBias instance
    media_bias = MediaBias(db)
    
    # Enable media bias enrichment
    media_bias.set_enabled(True)
    
    # Create Research instance
    research = Research(db)
    
    # Test URLs with known bias data
    test_urls = [
        'https://www.cnn.com/2023/01/01/politics/test-article',
        'https://www.foxnews.com/politics/test-article',
        'https://www.reuters.com/world/test-article',
        'https://www.nytimes.com/2023/01/01/us/test-article.html',
        'https://www.breitbart.com/politics/test-article',
        'https://www.bbc.co.uk/news/world-test-article',
    ]
    
    results = []
    
    for url in test_urls:
        print(f"\nTesting URL: {url}")
        source = urlparse(url).netloc
        
        # Check if we have bias data for this source
        bias_data = media_bias.get_bias_for_source(source)
        if bias_data:
            print(f"Found bias data for {source}: {bias_data.get('bias', 'Unknown')}, "
                  f"Factual: {bias_data.get('factual_reporting', 'Unknown')}")
        else:
            print(f"No bias data found for {source}")
            continue
        
        # Create test article data
        article_data = {
            'title': f'Test Article for Media Bias from {source}',
            'uri': url,
            'news_source': source,
            'summary': 'This is a test article to verify media bias integration.',
            'sentiment': 'Neutral',
            'time_to_impact': 'Short-term',
            'category': 'Technology',
            'future_signal': 'Trend',
            'future_signal_explanation': 'Test explanation',
            'publication_date': '2023-01-01',
            'topic': 'Test',
            'sentiment_explanation': 'Test sentiment explanation',
            'time_to_impact_explanation': 'Test time to impact explanation',
            'tags': ['test', 'media-bias'],
            'driver_type': 'Technological',
            'driver_type_explanation': 'Test driver explanation'
        }
        
        try:
            # Save article
            save_result = await research.save_article(article_data)
            print(f"Article saved: {save_result}")
            
            # Retrieve the saved article to verify bias data was added
            saved_article = db.get_article(url)
            if saved_article:
                print(f"Retrieved article: {saved_article['title']}")
                
                # Check if bias data was added
                if saved_article.get('bias'):
                    print(f"Bias data added successfully!")
                    print(f"Bias: {saved_article.get('bias', 'Not set')}")
                    print(f"Factual reporting: {saved_article.get('factual_reporting', 'Not set')}")
                    results.append({
                        'source': source,
                        'success': True,
                        'bias': saved_article.get('bias'),
                        'factual_reporting': saved_article.get('factual_reporting')
                    })
                else:
                    print("Bias data was not added to the article")
                    results.append({
                        'source': source,
                        'success': False,
                        'reason': 'Bias data not added'
                    })
            else:
                print("Failed to retrieve saved article")
                results.append({
                    'source': source,
                    'success': False,
                    'reason': 'Article not found after save'
                })
        except Exception as e:
            print(f"Error testing {source}: {str(e)}")
            results.append({
                'source': source,
                'success': False,
                'reason': str(e)
            })
        
        # Clean up - delete test article
        db.delete_article(url)
    
    # Print summary
    print("\n=== Media Bias Integration Test Summary ===")
    success_count = sum(1 for r in results if r.get('success', False))
    print(f"Tests completed: {len(results)}, Successful: {success_count}")
    
    for result in results:
        status = "✓" if result.get('success', False) else "✗"
        print(f"{status} {result['source']}: "
              f"{result.get('bias', 'N/A')}, {result.get('factual_reporting', 'N/A')}")


async def test_bulk_article_with_bias():
    """Test bulk article save with media bias data."""
    print("\n=== Testing Bulk Article Save with Media Bias ===")
    
    # Get database connection
    db = get_database_instance()
    
    # Create MediaBias instance and enable enrichment
    media_bias = MediaBias(db)
    media_bias.set_enabled(True)
    
    # Create test articles
    from app.bulk_research import BulkResearch
    bulk_research = BulkResearch(db)
    
    # Test URLs with different sources
    test_articles = [
        {
            'title': 'Test CNN Article',
            'uri': 'https://www.cnn.com/bulk-test/1',
            'news_source': 'www.cnn.com',
            'summary': 'This is a test CNN article',
            'sentiment': 'Neutral',
            'time_to_impact': 'Short-term',
            'category': 'Technology',
            'future_signal': 'Trend',
            'future_signal_explanation': 'Test explanation',
            'publication_date': '2023-01-01',
            'topic': 'Test',
            'sentiment_explanation': 'Test sentiment explanation',
            'time_to_impact_explanation': 'Test time to impact explanation',
            'tags': ['test', 'media-bias'],
            'driver_type': 'Technological',
            'driver_type_explanation': 'Test driver explanation',
            'submission_date': '2023-01-01',
            'analyzed': True
        },
        {
            'title': 'Test Fox News Article',
            'uri': 'https://www.foxnews.com/bulk-test/1',
            'news_source': 'www.foxnews.com',
            'summary': 'This is a test Fox News article',
            'sentiment': 'Neutral',
            'time_to_impact': 'Short-term',
            'category': 'Technology',
            'future_signal': 'Trend',
            'future_signal_explanation': 'Test explanation',
            'publication_date': '2023-01-01',
            'topic': 'Test',
            'sentiment_explanation': 'Test sentiment explanation',
            'time_to_impact_explanation': 'Test time to impact explanation',
            'tags': ['test', 'media-bias'],
            'driver_type': 'Technological',
            'driver_type_explanation': 'Test driver explanation',
            'submission_date': '2023-01-01',
            'analyzed': True
        }
    ]
    
    try:
        # Save bulk articles
        result = await bulk_research.save_bulk_articles(test_articles)
        print(f"Bulk save result: {len(result['success'])} successes, {len(result['errors'])} errors")
        
        # Verify bias data was added
        for article_info in test_articles:
            url = article_info['uri']
            source = article_info['news_source']
            
            # Get the saved article
            saved_article = db.get_article(url)
            if saved_article:
                if saved_article.get('bias'):
                    print(f"✓ {source}: Bias: {saved_article.get('bias')}, "
                          f"Factual: {saved_article.get('factual_reporting')}")
                else:
                    print(f"✗ {source}: No bias data added")
            else:
                print(f"✗ {source}: Article not found after save")
            
            # Clean up - delete test article
            db.delete_article(url)
            
    except Exception as e:
        print(f"Error in bulk test: {str(e)}")


async def main():
    """Run all tests."""
    print("=== Media Bias Integration Tests ===")
    
    # Test individual article save with bias data
    await test_save_article_with_bias()
    
    # Test bulk article save with bias data
    await test_bulk_article_with_bias()


if __name__ == "__main__":
    asyncio.run(main()) 