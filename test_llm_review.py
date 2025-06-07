#!/usr/bin/env python3
"""
Test script for LLM-based content review endpoint.
This tests the new functionality that detects unwanted content like cookie notices and paywalls.
"""

import requests
import json
import sys

def test_llm_content_review():
    """Test the LLM content review endpoint with various content types."""
    
    base_url = "http://localhost:8000"  # Adjust as needed
    endpoint = f"{base_url}/api/keyword-monitor/review-content"
    
    # Test cases for different content types
    test_cases = [
        {
            "name": "High Quality Article",
            "data": {
                "article_title": "Breakthrough in AI Research Leads to New Applications",
                "article_summary": "Researchers at Stanford University have developed a new machine learning algorithm that shows significant improvements in natural language processing tasks. The algorithm, called TransformerPlus, demonstrates 15% better performance than previous models on benchmark tests.",
                "article_source": "TechNews Daily",
                "model_name": "gpt-4o-mini"
            },
            "expected_quality": "high"
        },
        {
            "name": "Cookie Notice Content",
            "data": {
                "article_title": "Cookie Policy",
                "article_summary": "This website uses cookies to ensure you get the best experience on our website. By continuing to use this site, you agree to our cookie policy. Accept cookies to continue browsing.",
                "article_source": "Example.com",
                "model_name": "gpt-4o-mini"
            },
            "expected_quality": "low"
        },
        {
            "name": "Paywall Content", 
            "data": {
                "article_title": "Breaking News: Major Economic Changes",
                "article_summary": "Important economic developments are happening that could affect markets... Subscribe to continue reading this premium content. Sign up for full access to our exclusive analysis.",
                "article_source": "Financial Times",
                "model_name": "gpt-4o-mini"
            },
            "expected_quality": "low"
        },
        {
            "name": "Mixed Quality Content",
            "data": {
                "article_title": "Tech Industry Updates",
                "article_summary": "Recent developments in the technology sector include new product launches and market trends. Follow us on social media for more updates! Subscribe to our newsletter for weekly tech insights.",
                "article_source": "Tech Blog",
                "model_name": "gpt-4o-mini"
            },
            "expected_quality": "medium"
        }
    ]
    
    print("🔍 Testing LLM Content Review Endpoint")
    print("=" * 50)
    
    for i, test_case in enumerate(test_cases, 1):
        print(f"\n{i}. Testing: {test_case['name']}")
        print(f"   Title: {test_case['data']['article_title']}")
        print(f"   Summary: {test_case['data']['article_summary'][:60]}...")
        
        try:
            # Make the API request
            response = requests.post(
                endpoint,
                json=test_case['data'],
                headers={"Content-Type": "application/json"}
            )
            
            if response.status_code == 200:
                result = response.json()
                
                if result.get('success'):
                    review = result.get('review', {})
                    quality_score = review.get('quality_score', 0)
                    recommendation = review.get('recommendation', 'unknown')
                    issues = review.get('issues_detected', [])
                    content_type = review.get('content_type', 'unknown')
                    
                    print(f"   ✅ Success!")
                    print(f"   📊 Quality Score: {quality_score:.2f}")
                    print(f"   💡 Recommendation: {recommendation}")
                    print(f"   🏷️  Content Type: {content_type}")
                    
                    if issues:
                        print(f"   ⚠️  Issues Detected: {', '.join(issues[:3])}")
                        if len(issues) > 3:
                            print(f"      ... and {len(issues) - 3} more")
                    else:
                        print(f"   ✨ No issues detected")
                        
                    # Validate expected quality
                    expected = test_case['expected_quality']
                    if expected == "high" and quality_score >= 0.8:
                        print(f"   ✅ Quality expectation met (high)")
                    elif expected == "low" and quality_score <= 0.3:
                        print(f"   ✅ Quality expectation met (low)")
                    elif expected == "medium" and 0.3 < quality_score < 0.8:
                        print(f"   ✅ Quality expectation met (medium)")
                    else:
                        print(f"   ⚠️  Quality expectation not met (expected {expected}, got {quality_score:.2f})")
                        
                else:
                    print(f"   ❌ API returned error: {result.get('error', 'Unknown error')}")
                    if result.get('review'):
                        fallback_review = result['review']
                        print(f"   📊 Fallback Score: {fallback_review.get('quality_score', 'N/A')}")
                    
            else:
                print(f"   ❌ HTTP Error {response.status_code}")
                try:
                    error_data = response.json()
                    print(f"   Error: {error_data.get('detail', 'Unknown error')}")
                except:
                    print(f"   Error: {response.text}")
                    
        except requests.exceptions.ConnectionError:
            print(f"   ❌ Connection Error - Is the server running on {base_url}?")
        except Exception as e:
            print(f"   ❌ Unexpected Error: {str(e)}")
    
    print("\n" + "=" * 50)
    print("🎯 Test Summary:")
    print("✅ If you see quality scores and recommendations above, the LLM review is working!")
    print("📋 Expected behavior:")
    print("   - High quality articles: score > 0.8, recommendation 'approve'")
    print("   - Cookie/paywall content: score < 0.3, recommendation 'reject'")
    print("   - Mixed content: score 0.3-0.8, recommendation 'review'")
    print("\n🖱️  UI Features:")
    print("   - Review badges in the analysis modal are now clickable")
    print("   - Click any badge to see detailed LLM review rationale")
    print("   - View detected issues, explanations, and override decisions")
    print("   - Manual override functionality for review decisions")
    
if __name__ == "__main__":
    test_llm_content_review() 