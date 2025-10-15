#!/usr/bin/env python3
"""
Test script to re-analyze an article and see if the summary gets updated.
This will help us debug why AI-generated summaries aren't being saved.
"""

import sys
import os
import asyncio

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import Database
from app.bulk_research import BulkResearch
from app.research import Research

async def test_summary_update():
    """Test re-analyzing an article to see if summary gets updated."""

    # Test article URL
    test_url = "https://www.benzinga.com/pressreleases/25/10/n48191709/infosys-chosen-by-nhsbsa-to-deliver-a-new-workforce-management-solution-for-the-nhs-in-england-and"

    print(f"\n{'='*80}")
    print(f"Testing Summary Update for:")
    print(f"{test_url}")
    print(f"{'='*80}\n")

    # Initialize database
    db = Database()

    # Check current summary in database
    print("📊 BEFORE: Checking current database state...")
    conn = db._temp_get_connection()
    from sqlalchemy import select, text
    from app.database_models import t_articles

    result = conn.execute(
        select(t_articles.c.uri, t_articles.c.summary, t_articles.c.analyzed)
        .where(t_articles.c.uri == test_url)
    ).mappings().fetchone()

    if result:
        current_summary = result['summary']
        print(f"Current summary (first 150 chars): {current_summary[:150]}...")
        print(f"Summary length: {len(current_summary)} chars")
        print(f"Analyzed: {result['analyzed']}")
    else:
        print("❌ Article not found in database!")
        return

    # Initialize BulkResearch
    research = Research(db)
    bulk_research = BulkResearch(db, research)

    # Re-analyze the article
    print("\n🔍 ANALYZING: Re-analyzing article with AI...")
    results = await bulk_research.analyze_bulk_urls(
        urls=[test_url],
        summary_type="curious_ai",
        model_name="gpt-4.1-mini",
        summary_length=50,
        summary_voice="neutral",
        topic="AI and Machine Learning"
    )

    if results and len(results) > 0:
        analysis_result = results[0]
        print(f"\n✅ Analysis completed!")
        print(f"AI-generated summary (first 150 chars): {analysis_result.get('summary', '')[:150]}...")
        print(f"Summary length: {len(analysis_result.get('summary', ''))} chars")

        # Save the analysis
        print("\n💾 SAVING: Saving analysis to database...")
        save_results = await bulk_research.save_bulk_articles([analysis_result])

        if save_results['success']:
            print(f"✅ Save reported success for {len(save_results['success'])} articles")
        if save_results['errors']:
            print(f"❌ Save reported errors: {save_results['errors']}")

        # Check database again
        print("\n📊 AFTER: Checking database state after save...")
        result_after = conn.execute(
            select(t_articles.c.uri, t_articles.c.summary, t_articles.c.analyzed)
            .where(t_articles.c.uri == test_url)
        ).mappings().fetchone()

        if result_after:
            new_summary = result_after['summary']
            print(f"New summary (first 150 chars): {new_summary[:150]}...")
            print(f"Summary length: {len(new_summary)} chars")
            print(f"Analyzed: {result_after['analyzed']}")

            # Compare
            if new_summary != current_summary:
                print("\n✅ SUCCESS! Summary was updated!")
            else:
                print("\n❌ FAILURE! Summary was NOT updated!")
                print("The summary in the database is still the same.")
    else:
        print("❌ Analysis failed!")

    print(f"\n{'='*80}\n")

if __name__ == "__main__":
    asyncio.run(test_summary_update())
