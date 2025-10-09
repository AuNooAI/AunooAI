"""
Tests for Auto-Ingest Service
Tests topic ontology loading, relevance assessment, and score persistence.
"""
import pytest
import asyncio
from unittest.mock import Mock, patch, AsyncMock, MagicMock
from pathlib import Path
import json

from app.services.auto_ingest_service import AutoIngestService, AutoIngestConfig
from app.database import Database


@pytest.fixture
def mock_db():
    """Mock database instance"""
    db = Mock(spec=Database)
    db.connection = Mock()
    db.db_type = 'postgresql'
    db._temp_get_connection = Mock()
    return db


@pytest.fixture
def mock_config_json(tmp_path):
    """Create a mock config.json file"""
    config_data = {
        "topics": [
            {
                "name": "AI and Machine Learning",
                "description": "Comprehensive coverage of artificial intelligence and machine learning developments",
                "categories": [
                    "AI Business",
                    "AI Healthcare",
                    "AI Ethics",
                    "AI in Science"
                ],
                "future_signals": [
                    "AI is hype",
                    "AI will accelerate"
                ],
                "sentiment": [
                    "Positive",
                    "Neutral",
                    "Negative"
                ]
            },
            {
                "name": "Right-wing Rise in Europe",
                "description": "The rise and activities of the right wing in Europe",
                "categories": [
                    "Electoral Performance",
                    "Policy Influence",
                    "Public Sentiment and Protests"
                ]
            }
        ]
    }

    config_file = tmp_path / "config.json"
    config_file.write_text(json.dumps(config_data))
    return config_file


class TestAutoIngestServiceTopicOntology:
    """Test topic ontology loading from config.json"""

    def test_load_topics_config(self, mock_db, mock_config_json):
        """Test loading topics configuration from config.json"""
        service = AutoIngestService(db=mock_db)

        # Patch the config path to use our mock
        with patch.object(Path, '__truediv__', return_value=mock_config_json):
            topics_config = service._load_topics_config()

        assert len(topics_config) == 2
        assert "AI and Machine Learning" in topics_config
        assert "Right-wing Rise in Europe" in topics_config

        ai_topic = topics_config["AI and Machine Learning"]
        assert ai_topic["description"] == "Comprehensive coverage of artificial intelligence and machine learning developments"
        assert len(ai_topic["categories"]) == 4
        assert "AI Business" in ai_topic["categories"]

    def test_get_topic_description_with_categories(self, mock_db, mock_config_json):
        """Test formatting topic description with categories"""
        service = AutoIngestService(db=mock_db)

        # Mock the config loading
        service._topics_config = {
            "AI and Machine Learning": {
                "name": "AI and Machine Learning",
                "description": "AI and ML developments",
                "categories": ["AI Business", "AI Healthcare", "AI Ethics"]
            }
        }

        description = service._get_topic_description("AI and Machine Learning")

        assert description is not None
        assert "AI and ML developments" in description
        assert "Categories:" in description
        assert "AI Business" in description
        assert "AI Healthcare" in description
        assert "AI Ethics" in description

    def test_get_topic_description_without_categories(self, mock_db):
        """Test formatting topic description without categories"""
        service = AutoIngestService(db=mock_db)

        service._topics_config = {
            "Test Topic": {
                "name": "Test Topic",
                "description": "Test description only",
                "categories": []
            }
        }

        description = service._get_topic_description("Test Topic")

        assert description == "Test description only"
        assert "Categories:" not in description

    def test_get_topic_description_nonexistent(self, mock_db):
        """Test getting description for non-existent topic"""
        service = AutoIngestService(db=mock_db)
        service._topics_config = {}

        description = service._get_topic_description("Nonexistent Topic")

        assert description is None


class TestAutoIngestRelevanceAssessment:
    """Test relevance assessment with topic ontology"""

    @pytest.mark.asyncio
    async def test_assess_relevance_with_ontology(self, mock_db):
        """Test relevance assessment using full topic ontology"""
        service = AutoIngestService(db=mock_db)

        # Mock topic config
        service._topics_config = {
            "AI and Machine Learning": {
                "description": "AI developments",
                "categories": ["AI Business", "AI Healthcare"]
            }
        }

        # Mock articles
        articles = [
            {
                'url': 'https://example.com/ai-article',
                'title': 'New AI Breakthrough',
                'summary': 'Major advancement in AI technology',
                'source': 'TechNews',
                'topic': 'AI and Machine Learning',
                'keyword_ids': 'ai,machine learning'
            }
        ]

        # Mock the RelevanceCalculator
        with patch('app.services.auto_ingest_service.RelevanceCalculator') as MockRelevanceCalc:
            mock_calc = MockRelevanceCalc.return_value
            mock_calc.analyze_relevance.return_value = {
                'topic_alignment_score': 0.85,
                'keyword_relevance_score': 0.90,
                'confidence_score': 0.88,
                'category': 'AI Business'
            }

            results = await service.assess_relevance(articles)

        assert len(results) == 1
        article, relevance_data = results[0]

        assert article['url'] == 'https://example.com/ai-article'
        assert relevance_data['topic_alignment_score'] == 0.85
        assert relevance_data['keyword_relevance_score'] == 0.90
        assert relevance_data['confidence_score'] == 0.88

        # Verify analyze_relevance was called with topic_description
        mock_calc.analyze_relevance.assert_called_once()
        call_kwargs = mock_calc.analyze_relevance.call_args[1]
        assert 'topic_description' in call_kwargs
        assert 'AI developments' in call_kwargs['topic_description']
        assert 'AI Business' in call_kwargs['topic_description']

    @pytest.mark.asyncio
    async def test_assess_relevance_fallback_legacy(self, mock_db):
        """Test fallback to legacy method when topic config not found"""
        service = AutoIngestService(db=mock_db)
        service._topics_config = {}  # Empty config

        articles = [
            {
                'url': 'https://example.com/article',
                'title': 'Test Article',
                'summary': 'Test summary',
                'source': 'TestSource',
                'topic': 'Unknown Topic',
                'keyword_ids': 'test'
            }
        ]

        with patch('app.services.auto_ingest_service.RelevanceCalculator') as MockRelevanceCalc:
            mock_calc = MockRelevanceCalc.return_value
            mock_calc.calculate_topic_alignment.return_value = 0.65

            results = await service.assess_relevance(articles)

        assert len(results) == 1
        article, relevance_data = results[0]

        assert relevance_data['topic_alignment_score'] == 0.65
        # Legacy method doesn't provide keyword/confidence scores
        assert relevance_data.get('keyword_relevance_score') is None

        # Verify legacy method was called
        mock_calc.calculate_topic_alignment.assert_called_once()

    @pytest.mark.asyncio
    async def test_assess_relevance_error_handling(self, mock_db):
        """Test error handling in relevance assessment"""
        service = AutoIngestService(db=mock_db)
        service._topics_config = {
            "Test Topic": {
                "description": "Test",
                "categories": []
            }
        }

        articles = [
            {
                'url': 'https://example.com/article',
                'title': 'Test Article',
                'summary': 'Test',
                'source': 'Test',
                'topic': 'Test Topic',
                'keyword_ids': 'test'
            }
        ]

        with patch('app.services.auto_ingest_service.RelevanceCalculator') as MockRelevanceCalc:
            mock_calc = MockRelevanceCalc.return_value
            mock_calc.analyze_relevance.side_effect = Exception("LLM API Error")

            results = await service.assess_relevance(articles)

        # Should fallback to default low score on error
        assert len(results) == 1
        article, relevance_data = results[0]
        assert relevance_data['topic_alignment_score'] == 0.1


class TestAutoIngestPipeline:
    """Test the complete auto-ingest pipeline with relevance scores"""

    @pytest.mark.asyncio
    async def test_process_articles_batch_saves_relevance_scores(self, mock_db):
        """Test that relevance scores are saved during article processing"""
        service = AutoIngestService(db=mock_db)
        service.config.enabled = True
        service.config.quality_control_enabled = False
        service.config.min_relevance_threshold = 0.3

        # Mock topic config
        service._topics_config = {
            "AI and Machine Learning": {
                "description": "AI developments",
                "categories": ["AI Business"]
            }
        }

        articles = [
            {
                'alert_id': 1,
                'url': 'https://example.com/ai-article',
                'title': 'AI Advancement',
                'summary': 'New AI tech',
                'source': 'TechNews',
                'topic': 'AI and Machine Learning',
                'keyword_ids': 'ai',
                'publication_date': '2025-10-09',
                'group_name': 'AI Group'
            }
        ]

        # Mock RelevanceCalculator
        with patch('app.services.auto_ingest_service.RelevanceCalculator') as MockRelevanceCalc:
            mock_calc = MockRelevanceCalc.return_value
            mock_calc.analyze_relevance.return_value = {
                'topic_alignment_score': 0.85,
                'keyword_relevance_score': 0.90,
                'confidence_score': 0.88
            }

            # Mock BulkResearch
            with patch.object(service, 'bulk_research') as mock_bulk:
                mock_bulk.analyze_bulk_urls = AsyncMock(return_value=[{
                    'uri': 'https://example.com/ai-article',
                    'title': 'AI Advancement',
                    'category': 'AI Business',
                    'sentiment': 'Positive',
                    'analyzed': True
                }])

                mock_bulk.save_bulk_articles = AsyncMock(return_value={
                    'success': ['https://example.com/ai-article']
                })

                # Mock mark alert processed
                service._mark_alert_processed = AsyncMock()

                results = await service.process_articles_batch(articles)

        # Verify relevance scores were added before saving
        save_call_args = mock_bulk.save_bulk_articles.call_args[0][0]
        saved_article = save_call_args[0]

        assert saved_article['topic_alignment_score'] == 0.85
        assert saved_article['keyword_relevance_score'] == 0.90
        assert saved_article['confidence_score'] == 0.88
        assert saved_article['auto_ingested'] is True
        assert saved_article['ingest_status'] == 'auto'

        # Verify results
        assert results['ingested'] == 1
        assert results['rejected_relevance'] == 0
        assert results['errors'] == 0


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
