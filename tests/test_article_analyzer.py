from unittest.mock import Mock, patch
import pytest
import json
import os
from app.analyzers.article_analyzer import ArticleAnalyzer, ArticleAnalyzerError
from app.analyzers.prompt_templates import PromptTemplates, PromptTemplateError

@pytest.fixture
def mock_ai_model():
    model = Mock()
    model.generate_response = Mock()
    return model

@pytest.fixture
def custom_templates():
    return {
        "title_extraction": {
            "system_prompt": "Custom system prompt for title extraction",
            "user_prompt": "Custom user prompt for title extraction: {article_text}"
        },
        "content_analysis": {
            "system_prompt": "Custom system prompt for {summary_voice}",
            "user_prompt": "Custom analysis prompt for {title}"
        }
    }

@pytest.fixture
def custom_templates_file(tmp_path, custom_templates):
    file_path = tmp_path / "custom_templates.json"
    with open(file_path, 'w') as f:
        json.dump(custom_templates, f)
    return str(file_path)

@pytest.fixture
def analyzer(mock_ai_model):
    return ArticleAnalyzer(mock_ai_model)

@pytest.fixture
def analyzer_with_custom_templates(mock_ai_model, custom_templates_file):
    return ArticleAnalyzer(mock_ai_model, custom_templates_file)

def test_init_without_model():
    with pytest.raises(ArticleAnalyzerError, match="AI model is required"):
        ArticleAnalyzer(None)

def test_init_with_invalid_templates_path():
    with pytest.raises(ArticleAnalyzerError, match="Failed to initialize prompt templates"):
        ArticleAnalyzer(Mock(), "nonexistent/path.json")

def test_init_with_custom_templates(analyzer_with_custom_templates, custom_templates):
    assert isinstance(analyzer_with_custom_templates.prompt_templates, PromptTemplates)
    assert "Custom system prompt" in analyzer_with_custom_templates.prompt_templates.templates["title_extraction"]["system_prompt"]

def test_truncate_text():
    analyzer = ArticleAnalyzer(Mock())
    
    # Test no truncation needed
    text = "Short text"
    assert analyzer.truncate_text(text, max_chars=20) == text
    
    # Test truncation
    long_text = "This is a very long text that needs to be truncated"
    max_chars = 20
    truncated = analyzer.truncate_text(long_text, max_chars=max_chars)
    assert len(truncated) == max_chars + 3  # +3 for "..."
    assert truncated.endswith("...")
    
    # Test empty text
    assert analyzer.truncate_text("") == ""
    
    # Test invalid max_chars
    with pytest.raises(ArticleAnalyzerError, match="max_chars must be a positive integer"):
        analyzer.truncate_text("text", max_chars=0)
    with pytest.raises(ArticleAnalyzerError, match="max_chars must be a positive integer"):
        analyzer.truncate_text("text", max_chars=-1)
    with pytest.raises(ArticleAnalyzerError, match="max_chars must be a positive integer"):
        analyzer.truncate_text("text", max_chars="invalid")

def test_format_tags():
    analyzer = ArticleAnalyzer(Mock())
    
    # Test normal tags
    tags_str = "[AI, Machine Learning, Neural Networks]"
    expected = ["AI", "MachineLearning", "NeuralNetworks"]
    assert analyzer.format_tags(tags_str) == expected
    
    # Test empty tags
    assert analyzer.format_tags("[]") == []
    assert analyzer.format_tags("") == []
    
    # Test single tag
    assert analyzer.format_tags("[AI]") == ["AI"]
    
    # Test malformed tags
    with pytest.raises(ArticleAnalyzerError, match="Failed to format tags"):
        analyzer.format_tags(None)

def test_truncate_summary():
    analyzer = ArticleAnalyzer(Mock())
    
    # Test no truncation needed
    summary = "This is a short summary"
    max_words = 5
    assert analyzer.truncate_summary(summary, max_words) == summary
    
    # Test truncation
    long_summary = "This is a very long summary that needs to be truncated to fewer words"
    max_words = 5
    truncated = analyzer.truncate_summary(long_summary, max_words)
    assert len(truncated.split()) == max_words
    assert truncated == "This is a very long"
    
    # Test empty summary
    assert analyzer.truncate_summary("", 5) == ""
    
    # Test invalid max_words
    with pytest.raises(ArticleAnalyzerError, match="max_words must be a positive integer"):
        analyzer.truncate_summary("text", max_words=0)
    with pytest.raises(ArticleAnalyzerError, match="max_words must be a positive integer"):
        analyzer.truncate_summary("text", max_words=-1)
    with pytest.raises(ArticleAnalyzerError, match="max_words must be a positive integer"):
        analyzer.truncate_summary("text", max_words="invalid")

def test_parse_analysis():
    analyzer = ArticleAnalyzer(Mock())
    
    # Test normal analysis
    analysis = """
    Title: Test Title
    Summary: Test Summary
    Category: AI
    Future Signal: Positive
    Future Signal Explanation: Good progress
    Sentiment: Positive
    Time to Impact: Short Term
    Driver Type: Technology
    Tags: [tag1, tag2]
    """
    parsed = analyzer.parse_analysis(analysis)
    assert parsed["Title"] == "Test Title"
    assert parsed["Summary"] == "Test Summary"
    assert parsed["Category"] == "AI"
    assert parsed["Future Signal"] == "Positive"
    assert parsed["Future Signal Explanation"] == "Good progress"
    
    # Test empty analysis
    assert analyzer.parse_analysis("") == {}
    
    # Test malformed analysis
    malformed = """
    No colons here
    Just some text
    """
    with pytest.raises(ArticleAnalyzerError, match="Missing required fields"):
        analyzer.parse_analysis(malformed)
    
    # Test missing required fields
    incomplete = """
    Title: Test Title
    Summary: Test Summary
    """
    with pytest.raises(ArticleAnalyzerError, match="Missing required fields"):
        analyzer.parse_analysis(incomplete)

def test_extract_title_with_default_template(analyzer, mock_ai_model):
    # Setup mock response
    mock_ai_model.generate_response.return_value = "Generated Title"
    
    # Test title extraction
    article_text = "Some article content"
    title = analyzer.extract_title(article_text)
    
    # Verify the result
    assert title == "Generated Title"
    
    # Verify the mock was called correctly
    mock_ai_model.generate_response.assert_called_once()
    call_args = mock_ai_model.generate_response.call_args[0][0]
    
    # Verify the prompt structure
    assert len(call_args) == 2
    assert call_args[0]["role"] == "system"
    assert "expert editor" in call_args[0]["content"]
    assert call_args[1]["role"] == "user"
    assert article_text[:2000] in call_args[1]["content"]

def test_extract_title_with_custom_template(analyzer_with_custom_templates, mock_ai_model):
    # Setup mock response
    mock_ai_model.generate_response.return_value = "Generated Title"
    
    # Test title extraction
    article_text = "Some article content"
    title = analyzer_with_custom_templates.extract_title(article_text)
    
    # Verify the result
    assert title == "Generated Title"
    
    # Verify the mock was called correctly
    mock_ai_model.generate_response.assert_called_once()
    call_args = mock_ai_model.generate_response.call_args[0][0]
    
    # Verify custom template was used
    assert "Custom system prompt" in call_args[0]["content"]
    assert "Custom user prompt" in call_args[1]["content"]
    
    # Test empty article text
    with pytest.raises(ArticleAnalyzerError, match="Article text cannot be empty"):
        analyzer_with_custom_templates.extract_title("")
    
    # Test AI model failure
    mock_ai_model.generate_response.return_value = None
    with pytest.raises(ArticleAnalyzerError, match="Failed to generate title"):
        analyzer_with_custom_templates.extract_title("Some text")

def test_analyze_content_with_default_template(analyzer, mock_ai_model):
    # Setup mock response
    mock_response = """
    Title: Test Title
    Summary: Test Summary
    Category: Test Category
    Future Signal: Test Signal
    Future Signal Explanation: Test Explanation
    Sentiment: Positive
    Sentiment Explanation: Test Sentiment
    Time to Impact: Short Term
    Time to Impact Explanation: Test Impact
    Driver Type: Technology
    Driver Type Explanation: Test Driver
    Tags: [tag1, tag2, tag3]
    """
    mock_ai_model.generate_response.return_value = mock_response
    
    # Test parameters
    params = {
        "article_text": "Test article",
        "title": "Test title",
        "source": "test.com",
        "uri": "http://test.com",
        "summary_length": 100,
        "summary_voice": "expert",
        "summary_type": "analytical",
        "categories": ["Cat1", "Cat2"],
        "future_signals": ["Signal1", "Signal2"],
        "sentiment_options": ["Positive", "Negative"],
        "time_to_impact_options": ["Short", "Long"],
        "driver_types": ["Tech", "Social"]
    }
    
    # Call analyze_content
    result = analyzer.analyze_content(**params)
    
    # Verify the result
    assert isinstance(result, dict)
    assert "Title" in result
    assert "Summary" in result
    assert "Category" in result
    
    # Verify the mock was called correctly
    mock_ai_model.generate_response.assert_called_once()
    call_args = mock_ai_model.generate_response.call_args[0][0]
    
    # Verify the prompt structure
    assert len(call_args) == 2
    assert call_args[0]["role"] == "system"
    assert call_args[1]["role"] == "user"
    assert params["article_text"] in call_args[1]["content"]
    assert str(params["summary_length"]) in call_args[1]["content"]
    assert params["summary_voice"] in call_args[1]["content"]

def test_analyze_content_with_custom_template(analyzer_with_custom_templates, mock_ai_model):
    # Setup mock response
    mock_response = """
    Title: Test Title
    Summary: Test Summary
    Category: Test Category
    Future Signal: Test Signal
    Future Signal Explanation: Test Explanation
    Sentiment: Positive
    Sentiment Explanation: Test Sentiment
    Time to Impact: Short Term
    Time to Impact Explanation: Test Impact
    Driver Type: Technology
    Driver Type Explanation: Test Driver
    Tags: [tag1, tag2, tag3]
    """
    mock_ai_model.generate_response.return_value = mock_response
    
    # Test parameters
    params = {
        "article_text": "Test article",
        "title": "Test title",
        "source": "test.com",
        "uri": "http://test.com",
        "summary_length": 100,
        "summary_voice": "expert",
        "summary_type": "analytical",
        "categories": ["Cat1", "Cat2"],
        "future_signals": ["Signal1", "Signal2"],
        "sentiment_options": ["Positive", "Negative"],
        "time_to_impact_options": ["Short", "Long"],
        "driver_types": ["Tech", "Social"]
    }
    
    # Call analyze_content
    result = analyzer_with_custom_templates.analyze_content(**params)
    
    # Verify the result
    assert isinstance(result, dict)
    assert "Title" in result
    assert "Summary" in result
    assert "Category" in result
    
    # Verify the mock was called correctly
    mock_ai_model.generate_response.assert_called_once()
    call_args = mock_ai_model.generate_response.call_args[0][0]
    
    # Verify custom template was used
    assert "Custom system prompt" in call_args[0]["content"]
    assert "Custom analysis prompt" in call_args[1]["content"]
    
    # Test missing required parameters
    invalid_params = params.copy()
    invalid_params["article_text"] = ""
    with pytest.raises(ArticleAnalyzerError, match="Article text cannot be empty"):
        analyzer_with_custom_templates.analyze_content(**invalid_params)
    
    invalid_params = params.copy()
    invalid_params["categories"] = []
    with pytest.raises(ArticleAnalyzerError, match="Categories list cannot be empty"):
        analyzer_with_custom_templates.analyze_content(**invalid_params)

def test_analyze_content_error_handling(analyzer, mock_ai_model):
    # Setup mock to raise an exception
    mock_ai_model.generate_response.side_effect = Exception("API Error")
    
    # Test parameters
    params = {
        "article_text": "Test article",
        "title": "Test title",
        "source": "test.com",
        "uri": "http://test.com",
        "summary_length": 100,
        "summary_voice": "expert",
        "summary_type": "analytical",
        "categories": ["Cat1", "Cat2"],
        "future_signals": ["Signal1", "Signal2"],
        "sentiment_options": ["Positive", "Negative"],
        "time_to_impact_options": ["Short", "Long"],
        "driver_types": ["Tech", "Social"]
    }
    
    # Verify that the error is propagated
    with pytest.raises(ArticleAnalyzerError, match="Failed to analyze content"):
        analyzer.analyze_content(**params)
        
    # Test empty AI response
    mock_ai_model.generate_response.side_effect = None
    mock_ai_model.generate_response.return_value = None
    with pytest.raises(ArticleAnalyzerError, match="Failed to generate analysis"):
        analyzer.analyze_content(**params)

def test_analyze_content_with_cache(analyzer, mock_ai_model, tmp_path):
    # Setup mock response
    mock_response = """
    Title: Test Title
    Summary: Test Summary
    Category: Test Category
    Future Signal: Test Signal
    Future Signal Explanation: Test Explanation
    Sentiment: Positive
    Sentiment Explanation: Test Sentiment
    Time to Impact: Short Term
    Time to Impact Explanation: Test Impact
    Driver Type: Technology
    Driver Type Explanation: Test Driver
    Tags: [tag1, tag2, tag3]
    """
    mock_ai_model.generate_response.return_value = mock_response
    
    # Test parameters
    params = {
        "article_text": "Test article",
        "title": "Test title",
        "source": "test.com",
        "uri": "http://test.com",
        "summary_length": 100,
        "summary_voice": "expert",
        "summary_type": "analytical",
        "categories": ["Cat1", "Cat2"],
        "future_signals": ["Signal1", "Signal2"],
        "sentiment_options": ["Positive", "Negative"],
        "time_to_impact_options": ["Short", "Long"],
        "driver_types": ["Tech", "Social"]
    }
    
    # First call should use AI model
    result1 = analyzer.analyze_content(**params)
    assert mock_ai_model.generate_response.call_count == 1
    
    # Second call should use cache
    result2 = analyzer.analyze_content(**params)
    assert mock_ai_model.generate_response.call_count == 1  # Count shouldn't increase
    assert result1 == result2

def test_analyze_content_without_cache(analyzer, mock_ai_model):
    # Setup mock response
    mock_response = """
    Title: Test Title
    Summary: Test Summary
    Category: Test Category
    Future Signal: Test Signal
    Future Signal Explanation: Test Explanation
    Sentiment: Positive
    Sentiment Explanation: Test Sentiment
    Time to Impact: Short Term
    Time to Impact Explanation: Test Impact
    Driver Type: Technology
    Driver Type Explanation: Test Driver
    Tags: [tag1, tag2, tag3]
    """
    mock_ai_model.generate_response.return_value = mock_response
    
    # Test parameters
    params = {
        "article_text": "Test article",
        "title": "Test title",
        "source": "test.com",
        "uri": "http://test.com",
        "summary_length": 100,
        "summary_voice": "expert",
        "summary_type": "analytical",
        "categories": ["Cat1", "Cat2"],
        "future_signals": ["Signal1", "Signal2"],
        "sentiment_options": ["Positive", "Negative"],
        "time_to_impact_options": ["Short", "Long"],
        "driver_types": ["Tech", "Social"],
        "use_cache": False
    }
    
    # Both calls should use AI model
    analyzer.analyze_content(**params)
    analyzer.analyze_content(**params)
    assert mock_ai_model.generate_response.call_count == 2

def test_cache_operations(analyzer, mock_ai_model, sample_analysis):
    # Setup mock response
    mock_ai_model.generate_response.return_value = """
    Title: Test Title
    Summary: Test Summary
    Category: Test Category
    Future Signal: Test Signal
    Future Signal Explanation: Test Explanation
    Sentiment: Positive
    Sentiment Explanation: Test Sentiment
    Time to Impact: Short Term
    Time to Impact Explanation: Test Impact
    Driver Type: Technology
    Driver Type Explanation: Test Driver
    Tags: [tag1, tag2, tag3]
    """
    
    # Test parameters
    params = {
        "article_text": "Test article",
        "title": "Test title",
        "source": "test.com",
        "uri": "http://test.com",
        "summary_length": 100,
        "summary_voice": "expert",
        "summary_type": "analytical",
        "categories": ["Cat1", "Cat2"],
        "future_signals": ["Signal1", "Signal2"],
        "sentiment_options": ["Positive", "Negative"],
        "time_to_impact_options": ["Short", "Long"],
        "driver_types": ["Tech", "Social"]
    }
    
    # Analyze content to populate cache
    analyzer.analyze_content(**params)
    
    # Get cache stats
    stats = analyzer.get_cache_stats()
    assert stats["total_files"] == 1
    assert stats["total_size_bytes"] > 0
    
    # Clear cache
    analyzer.clear_cache()
    stats = analyzer.get_cache_stats()
    assert stats["total_files"] == 0
    
    # Analyze again to repopulate cache
    analyzer.analyze_content(**params)
    
    # Clean up expired (none should be expired)
    cleaned = analyzer.cleanup_expired_cache()
    assert cleaned == 0

def test_content_hash_consistency(analyzer):
    content1 = "Test content"
    content2 = "Different content"
    
    hash1a = analyzer._compute_content_hash(content1)
    hash1b = analyzer._compute_content_hash(content1)
    hash2 = analyzer._compute_content_hash(content2)
    
    # Same content should produce same hash
    assert hash1a == hash1b
    # Different content should produce different hashes
    assert hash1a != hash2

def test_cache_with_different_params(analyzer, mock_ai_model):
    # Setup mock response
    mock_response = """
    Title: Test Title
    Summary: Test Summary
    Category: Test Category
    Future Signal: Test Signal
    Future Signal Explanation: Test Explanation
    Sentiment: Positive
    Sentiment Explanation: Test Sentiment
    Time to Impact: Short Term
    Time to Impact Explanation: Test Impact
    Driver Type: Technology
    Driver Type Explanation: Test Driver
    Tags: [tag1, tag2, tag3]
    """
    mock_ai_model.generate_response.return_value = mock_response
    
    # Base parameters
    params = {
        "article_text": "Test article",
        "title": "Test title",
        "source": "test.com",
        "uri": "http://test.com",
        "summary_length": 100,
        "summary_voice": "expert",
        "summary_type": "analytical",
        "categories": ["Cat1", "Cat2"],
        "future_signals": ["Signal1", "Signal2"],
        "sentiment_options": ["Positive", "Negative"],
        "time_to_impact_options": ["Short", "Long"],
        "driver_types": ["Tech", "Social"]
    }
    
    # First call with original params
    analyzer.analyze_content(**params)
    assert mock_ai_model.generate_response.call_count == 1
    
    # Change non-content parameters shouldn't use cache
    params_different = params.copy()
    params_different["summary_length"] = 200
    analyzer.analyze_content(**params_different)
    assert mock_ai_model.generate_response.call_count == 2
    
    # Change content should not use cache
    params_different = params.copy()
    params_different["article_text"] = "Different article"
    analyzer.analyze_content(**params_different)
    assert mock_ai_model.generate_response.call_count == 3 