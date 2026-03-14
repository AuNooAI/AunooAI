#!/usr/bin/env python3
"""
Test script to verify the optimized SLM-only pipeline.
Confirms that LLM is NOT called when all SLM services are available.
"""

import asyncio
import sys
import os

# Add the parent directory to the path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import get_database_instance
from app.services.automated_ingest_service import AutomatedIngestService


async def test_slm_only_pipeline():
    """Test that LLM is skipped when all SLM services available."""

    print("=" * 60)
    print("Testing SLM-Only Pipeline (LLM Skip Optimization)")
    print("=" * 60)

    # Test articles with different content types
    test_articles = [
        {
            'uri': 'test://slm-pipeline-1',
            'title': 'OpenAI Announces GPT-5 with Revolutionary Reasoning Capabilities',
            'summary': '''OpenAI has unveiled GPT-5, its latest large language model featuring
            significantly improved reasoning capabilities. The new model demonstrates a 40%
            improvement in complex problem-solving tasks and shows near-human performance on
            graduate-level mathematics. CEO Sam Altman stated that GPT-5 represents a major
            step toward artificial general intelligence. The model will be available through
            API access starting next month, with pricing expected to be competitive with
            current offerings.''',
            'news_source': 'TechCrunch',
        },
        {
            'uri': 'test://slm-pipeline-2',
            'title': 'EU Passes Comprehensive AI Regulation Bill',
            'summary': '''The European Parliament has approved the AI Act, the world\'s first
            comprehensive framework for regulating artificial intelligence. The legislation
            imposes strict requirements on high-risk AI systems including mandatory risk
            assessments, transparency requirements, and human oversight provisions. Companies
            face fines of up to 6% of global revenue for non-compliance. The law takes effect
            in 24 months, giving businesses time to adapt their AI deployments.''',
            'news_source': 'Reuters',
        },
        {
            'uri': 'test://slm-pipeline-3',
            'title': 'Tech Layoffs Continue as Microsoft Cuts 10,000 Jobs',
            'summary': '''Microsoft has announced plans to lay off 10,000 employees, roughly 5%
            of its workforce, as the technology sector continues to shed jobs amid economic
            uncertainty. The cuts will affect departments across the company including Azure,
            gaming, and HR divisions. CEO Satya Nadella cited the need to "align our cost
            structure with revenue" while continuing to invest in strategic AI initiatives.
            This follows similar layoffs at Google, Amazon, and Meta in recent months.''',
            'news_source': 'Wall Street Journal',
        },
    ]

    topic = 'AI and Machine Learning'
    test_article = test_articles[0]  # Use first article for detailed test

    # Initialize service
    db = get_database_instance()
    service = AutomatedIngestService(db)

    # Check service availability
    print("\n1. Checking SLM service availability...")

    from app.services.summarization_service import get_summarization_service
    from app.services.enrichment_service import get_enrichment_service
    from app.services.explanation_service import get_explanation_service
    from app.services.category_service import get_category_service
    from app.services.keybert_tagging_service import get_keybert_tagging_service

    summarization = get_summarization_service()
    enrichment = get_enrichment_service()
    explanation = get_explanation_service()
    category = get_category_service()
    tagging = get_keybert_tagging_service()

    print(f"   Summarization (Phi-3): {'✅ Available' if summarization.is_available() else '❌ Unavailable'}")
    print(f"   Enrichment (DeBERTa): {'✅ Available' if enrichment.is_available() else '❌ Unavailable'}")
    print(f"   Explanation (Qwen): {'✅ Available' if explanation.is_available() else '❌ Unavailable'}")
    print(f"   Category (Qwen): {'✅ Available' if category.is_available() else '❌ Unavailable'}")
    print(f"   Hybrid Tagging (KeyBERT+Phi-3): {'✅ Available' if tagging.is_hybrid_available() else '❌ Unavailable'}")

    all_available = (
        summarization.is_available() and
        enrichment.is_available() and
        explanation.is_available() and
        category.is_available() and
        tagging.is_hybrid_available()
    )

    if all_available:
        print("\n   ✨ All SLM services available - LLM call should be SKIPPED!")
    else:
        print("\n   ⚠️ Some SLM services unavailable - LLM will be used as fallback")

    # Run the enrichment pipeline
    print("\n2. Running enrichment pipeline...")
    print("-" * 60)

    result = await service._analyze_article_content_async(test_article.copy(), topic)

    print("-" * 60)

    # Analyze results
    print("\n3. Results:")
    method = result.get('_enrichment_method', 'unknown')
    print(f"   Enrichment method: {method}")
    print(f"   Summary source: {result.get('_summary_source', 'unknown')}")
    print(f"   Category: {result.get('category')}")
    print(f"   Sentiment: {result.get('sentiment')}")
    print(f"   Time to Impact: {result.get('time_to_impact')}")
    print(f"   Driver Type: {result.get('driver_type')}")
    print(f"   Future Signal: {result.get('future_signal')}")

    # Check if LLM was used
    if 'hybrid_slm' in method or 'slm' in method.lower():
        components = method.split('(')[1].rstrip(')').split(',') if '(' in method else []
        print(f"\n   SLM Components used: {len(components)}")
        for comp in components:
            print(f"      - {comp}")

    # Print explanations
    print("\n4. Explanations (from Qwen):")
    for field in ['sentiment', 'time_to_impact', 'driver_type', 'future_signal']:
        explanation_text = result.get(f'{field}_explanation')
        if explanation_text:
            print(f"   {field}: {explanation_text[:100]}...")

    print("\n" + "=" * 60)
    if all_available and 'llm_only' not in method:
        print("✅ SUCCESS: Pipeline ran with SLM optimization")
    elif 'llm_only' in method:
        print("❌ ISSUE: LLM was used for all fields")
    else:
        print("⚠️ Mixed mode: Some components from SLM, some from LLM")
    print("=" * 60)

    # Test all articles and show examples
    print("\n\n" + "=" * 60)
    print("EXAMPLE OUTPUTS FROM MULTIPLE ARTICLES")
    print("=" * 60)

    for i, article in enumerate(test_articles):
        print(f"\n--- Article {i+1}: {article['title'][:50]}... ---")
        article_result = await service._analyze_article_content_async(article.copy(), topic)

        print(f"\n📊 Classification Results:")
        print(f"   Category: {article_result.get('category')}")
        print(f"   Sentiment: {article_result.get('sentiment')}")
        print(f"   Time to Impact: {article_result.get('time_to_impact')}")
        print(f"   Driver Type: {article_result.get('driver_type')}")
        print(f"   Future Signal: {article_result.get('future_signal')}")
        print(f"   Tags: {article_result.get('tags')}")

        print(f"\n💬 Explanations:")
        for field in ['sentiment', 'time_to_impact', 'driver_type', 'future_signal']:
            exp = article_result.get(f'{field}_explanation', '')
            if exp:
                print(f"   {field}: {exp[:120]}{'...' if len(exp) > 120 else ''}")

        print(f"\n📝 Summary Preview:")
        summary = article_result.get('summary', '')
        print(f"   {summary[:200]}{'...' if len(summary) > 200 else ''}")

        method = article_result.get('_enrichment_method', 'unknown')
        print(f"\n🔧 Method: {method}")
        print("-" * 60)

    return result


if __name__ == "__main__":
    result = asyncio.run(test_slm_only_pipeline())
