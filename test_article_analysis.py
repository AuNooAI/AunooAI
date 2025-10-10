#!/usr/bin/env python3
"""
Test script to verify article analysis generates all explanation fields.
This will analyze a test article and show which fields are generated.
"""

import sys
import os
import asyncio
sys.path.insert(0, '/home/orochford/tenants/skunkworkx.aunoo.ai')

from app.research import Research
from app.database import Database
import json

# Sample article text
TEST_ARTICLE_URL = "https://www.example.com/test-ai-regulation-2025"
TEST_ARTICLE_TEXT = """
AI Industry Faces Major Disruption as New Regulation Announced

Published: October 10, 2025

The tech industry was caught off guard today as regulators announced sweeping new rules
governing artificial intelligence development and deployment. The new framework will require
companies to obtain approval before releasing AI models to the public, and mandates extensive
safety testing and documentation.

Major tech companies have expressed concerns about the regulations, arguing they could stifle
innovation and give an advantage to foreign competitors not subject to the same rules. However,
consumer advocacy groups have praised the move, saying it's necessary to protect the public
from potentially dangerous AI systems.

The regulations will take effect in six months, giving companies time to prepare for compliance.
Industry analysts predict this could significantly slow down the pace of AI releases in the near term.

Some experts argue that these regulations are necessary to prevent potential harms from advanced
AI systems, while others worry about the economic impact on the tech sector. The debate is likely
to continue as the industry adapts to this new regulatory landscape.
"""

async def test_article_analysis():
    """Test article analysis with a sample article."""

    try:
        # Initialize Research instance
        print("\n🔧 Initializing Research instance...")
        db = Database()
        research = Research(db=db)

        # Get available topics
        topics = research.get_topics()
        if not topics:
            print("❌ No topics found in config")
            return

        topic_name = topics[0] if isinstance(topics, list) else list(topics.keys())[0]
        print(f"✅ Using topic: {topic_name}")

        # Set the topic
        research.set_topic(topic_name)
        print(f"✅ Topic set to: {topic_name}")

        # Analyze the article
        print("\n🔍 Starting article analysis...")
        print(f"   URL: {TEST_ARTICLE_URL}")
        print(f"   Article length: {len(TEST_ARTICLE_TEXT)} characters")

        result = await research.analyze_article(
            uri=TEST_ARTICLE_URL,
            article_text=TEST_ARTICLE_TEXT,
            title="AI Industry Faces Major Disruption as New Regulation Announced",
            source="Test News Network"
        )

        print("\n✅ Analysis completed!")
        print("\n" + "="*80)
        print("ANALYSIS RESULT")
        print("="*80)

        # Check for explanation fields
        explanation_fields = [
            'future_signal_explanation',
            'sentiment_explanation',
            'time_to_impact_explanation',
            'driver_type_explanation'
        ]

        print("\n📝 EXPLANATION FIELDS STATUS:")
        for field in explanation_fields:
            value = result.get(field, '')
            status = "✅ PRESENT" if value else "❌ MISSING"
            print(f"\n{status}: {field}")
            if value:
                # Show first 150 chars
                display_value = str(value)[:150]
                if len(str(value)) > 150:
                    display_value += "..."
                print(f"   Value: {display_value}")

        # Show main classification fields
        print("\n📊 MAIN CLASSIFICATION FIELDS:")
        main_fields = [
            'category',
            'future_signal',
            'sentiment',
            'time_to_impact',
            'driver_type'
        ]
        for field in main_fields:
            value = result.get(field, 'NOT SET')
            print(f"   {field}: {value}")

        print("\n" + "="*80)
        print("FULL RESULT (JSON):")
        print("="*80)
        # Print formatted JSON
        print(json.dumps(result, indent=2, default=str))

        # Summary
        print("\n" + "="*80)
        print("TEST SUMMARY:")
        print("="*80)
        missing = [f for f in explanation_fields if not result.get(f)]
        if missing:
            print(f"❌ Missing explanation fields: {', '.join(missing)}")
            print("\n⚠️  ISSUE IDENTIFIED:")
            print("   The AI analysis is NOT generating these explanation fields.")
            print("   This explains why newer articles (July-Oct 2025) lack this data.")
            print("\n🔧 NEXT STEPS:")
            print("   1. Check the prompt templates in app/analyzers/prompt_templates.py")
            print("   2. Verify the AI model is being asked to generate these explanations")
            print("   3. May need to update the analysis prompt to include these fields")
        else:
            print("✅ All explanation fields are present!")
            print("   The analysis system is working correctly.")

        return result

    except Exception as e:
        print(f"\n❌ Error during analysis: {str(e)}")
        import traceback
        traceback.print_exc()
        return None

if __name__ == "__main__":
    print("="*80)
    print("ARTICLE ANALYSIS EXPLANATION FIELD TEST")
    print("="*80)
    print("\nThis test will analyze a sample article and check if all")
    print("explanation fields are being generated by the AI model.\n")

    # Run the async test
    asyncio.run(test_article_analysis())
