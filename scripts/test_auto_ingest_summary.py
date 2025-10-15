#!/usr/bin/env python3
"""
Test script to verify that automated_ingest_service correctly extracts AI-generated summaries.
This tests the fix for the bug where summaries were not being extracted from analysis results.
"""

import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import Database
from app.services.automated_ingest_service import AutomatedIngestService

def test_auto_ingest_summary_extraction():
    """Test that auto-ingest correctly extracts AI-generated summaries from analysis results."""

    print(f"\n{'='*80}")
    print(f"Testing Auto-Ingest Summary Extraction Fix")
    print(f"Testing that analyze_article_content() includes AI summary in result")
    print(f"{'='*80}\n")

    # Initialize database and service
    db = Database()
    ingest_service = AutomatedIngestService(db)

    # Simulate article data as it would come from NewsAPI collector
    # This mimics what keyword monitoring stores: NewsAPI description in summary field
    article_data = {
        'uri': 'https://www.example.com/test-article',
        'title': 'Test Article About AI in Healthcare',
        'news_source': 'example.com',
        'publication_date': '2025-10-15',
        'summary': 'This is a truncated NewsAPI description that ends abruptly and should be replaced by AI...',  # Simulating NewsAPI description
        'topic': 'AI and Machine Learning',
        'analyzed': False
    }

    # Store original summary before analysis (need to copy since dict may be mutated)
    original_summary = article_data['summary']
    original_length = len(original_summary)

    print("📊 BEFORE ANALYSIS:")
    print(f"   Summary: {original_summary}")
    print(f"   Summary length: {original_length} chars")
    print(f"   Analyzed: {article_data.get('analyzed', False)}")
    print()

    try:
        # Call analyze_article_content() - the method we fixed
        print("🔍 ANALYZING: Calling analyze_article_content()...")
        enriched_article = ingest_service.analyze_article_content(article_data)

        print("✅ Analysis completed!")
        print()

        # Check if the summary was updated
        print("📊 AFTER ANALYSIS:")
        new_summary = enriched_article.get('summary', '')
        print(f"   Summary: {new_summary[:150]}..." if len(new_summary) > 150 else f"   Summary: {new_summary}")
        print(f"   Summary length: {len(new_summary)} chars")
        print(f"   Category: {enriched_article.get('category', 'N/A')}")
        print(f"   Sentiment: {enriched_article.get('sentiment', 'N/A')}")
        print(f"   Future Signal: {enriched_article.get('future_signal', 'N/A')}")
        print(f"   Analyzed: {enriched_article.get('analyzed', False)}")
        print()

        # Verify the fix worked - compare with original summary we saved earlier
        if new_summary and new_summary != original_summary and len(new_summary) > 50:
            print("✅ SUCCESS! AI-generated summary was extracted correctly!")
            print(f"   Summary changed from {original_length} to {len(new_summary)} chars")
            print(f"   AI metadata also present: category={enriched_article.get('category')}, sentiment={enriched_article.get('sentiment')}")
            return True
        else:
            print("❌ FAILURE! Summary was NOT properly extracted!")
            print(f"   Original summary: '{original_summary[:100]}'")
            print(f"   New summary: '{new_summary[:100]}'")
            print("   The summary field should contain AI-generated summary, not NewsAPI description")
            return False

    except Exception as e:
        print(f"\n❌ ERROR during analysis: {str(e)}")
        import traceback
        traceback.print_exc()
        return False

    finally:
        print(f"\n{'='*80}\n")

if __name__ == "__main__":
    success = test_auto_ingest_summary_extraction()
    sys.exit(0 if success else 1)
