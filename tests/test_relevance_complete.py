#!/usr/bin/env python3
"""
Comprehensive test for relevance analysis implementation
"""
import sys
import json
from app.database import Database
from app.relevance import RelevanceCalculator
from app.analyzers.prompt_templates import PromptTemplates

def test_database_schema():
    """Test that relevance columns exist in articles table"""
    print("🔍 Testing database schema...")
    db = Database()
    with db.get_connection() as conn:
        cursor = conn.cursor()
        if db.db_type == 'postgresql':
            cursor.execute(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_schema = 'public' AND table_name = 'articles'"
            )
            columns = [col[0] for col in cursor.fetchall()]
        else:
            cursor.execute('PRAGMA table_info(articles)')
            columns = [col[1] for col in cursor.fetchall()]
        
        expected_cols = [
            'topic_alignment_score',
            'keyword_relevance_score', 
            'confidence_score',
            'overall_match_explanation',
            'extracted_article_topics',
            'extracted_article_keywords'
        ]
        
        missing_cols = [col for col in expected_cols if col not in columns]
        if missing_cols:
            print(f"❌ Missing columns: {missing_cols}")
            return False
        
        print(f"✅ All {len(expected_cols)} relevance columns found")
        return True

def test_prompt_templates():
    """Test that relevance analysis prompt template works"""
    print("🔍 Testing prompt templates...")
    try:
        templates = PromptTemplates()
        prompt = templates.format_relevance_analysis_prompt(
            title='Test Article Title',
            source='test-source.com',
            content='Test article content about AI and technology',
            topic='Technology Trends',
            keywords='AI, technology, innovation'
        )
        
        if not prompt or len(prompt) != 2 or not prompt[0].get('content') or not prompt[1].get('content'):
            print("❌ Prompt template format is incorrect")
            return False
            
        print("✅ Relevance analysis prompt template working")
        return True
    except Exception as e:
        print(f"❌ Prompt template error: {e}")
        return False

def test_relevance_calculator():
    """Test RelevanceCalculator initialization"""
    print("🔍 Testing RelevanceCalculator...")
    try:
        calc = RelevanceCalculator('gpt-3.5-turbo')
        print("✅ RelevanceCalculator initialization successful")
        return True
    except Exception as e:
        print(f"❌ RelevanceCalculator error: {e}")
        return False

def test_template_syntax():
    """Test that the updated template has valid syntax"""
    print("🔍 Testing template syntax...")
    try:
        from jinja2 import Template
        from pathlib import Path
        
        content = Path('templates/keyword_alerts.html').read_text()
        Template(content)
        print("✅ Template syntax is valid")
        return True
    except Exception as e:
        print(f"❌ Template syntax error: {e}")
        return False

def main():
    print("=" * 60)
    print("COMPREHENSIVE RELEVANCE ANALYSIS IMPLEMENTATION TEST")
    print("=" * 60)
    
    tests = [
        test_database_schema,
        test_prompt_templates, 
        test_relevance_calculator,
        test_template_syntax
    ]
    
    results = []
    for test in tests:
        try:
            result = test()
            results.append(result)
        except Exception as e:
            print(f"❌ Test {test.__name__} failed with exception: {e}")
            results.append(False)
        print()
    
    passed = sum(results)
    total = len(results)
    
    print("=" * 60)
    print(f"RESULTS: {passed}/{total} tests passed")
    
    if passed == total:
        print("🎉 ALL TESTS PASSED! Relevance analysis is ready to use!")
        print("\nNext steps:")
        print("1. Start your FastAPI server")
        print("2. Go to the keyword alerts dashboard")
        print("3. Select articles and click 'Analyze Relevance'")
        print("4. Choose an AI model and run the analysis")
        print("5. See relevance scores appear in the table with tooltips")
    else:
        print("❌ Some tests failed. Please check the errors above.")
        sys.exit(1)

if __name__ == "__main__":
    main() 