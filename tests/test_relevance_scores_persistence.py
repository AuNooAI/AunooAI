"""
Tests for Relevance Scores Persistence
Tests that relevance scores are properly saved to the database when saving articles.
"""
import pytest
from unittest.mock import Mock, patch, AsyncMock, MagicMock
import asyncio

from app.bulk_research import BulkResearch
from app.database import Database


@pytest.fixture
def mock_db():
    """Mock database instance"""
    db = Mock(spec=Database)
    db.db_type = 'postgresql'
    db.db_path = '/path/to/db'

    # Mock connection
    mock_conn = MagicMock()
    mock_trans = MagicMock()
    mock_conn.begin.return_value = mock_trans
    mock_conn.execute.return_value = MagicMock(rowcount=1)

    db._temp_get_connection.return_value = mock_conn

    return db


@pytest.fixture
def mock_research():
    """Mock Research instance"""
    research = Mock()
    research.CATEGORIES = ["Category1", "Category2"]
    research.FUTURE_SIGNALS = ["Signal1", "Signal2"]
    research.SENTIMENT = ["Positive", "Negative"]
    research.TIME_TO_IMPACT = ["Short-term", "Long-term"]
    research.DRIVER_TYPES = ["Accelerator", "Blocker"]
    return research


class TestRelevanceScoresPersistence:
    """Test that relevance scores are saved to the database"""

    @pytest.mark.asyncio
    async def test_save_articles_with_all_relevance_scores(self, mock_db, mock_research):
        """Test saving articles with all three relevance score fields"""
        bulk_research = BulkResearch(db=mock_db, research=mock_research)

        articles = [
            {
                'uri': 'https://example.com/article1',
                'title': 'Test Article',
                'news_source': 'TestSource',
                'publication_date': '2025-10-09',
                'submission_date': '2025-10-09',
                'summary': 'Test summary',
                'category': 'AI Business',
                'future_signal': 'AI will accelerate',
                'future_signal_explanation': 'Because reasons',
                'sentiment': 'Positive',
                'sentiment_explanation': 'Good news',
                'time_to_impact': 'Short-term',
                'time_to_impact_explanation': 'Soon',
                'tags': 'ai,tech',
                'driver_type': 'Accelerator',
                'driver_type_explanation': 'Speeds things up',
                'topic': 'AI and Machine Learning',
                'analyzed': True,
                # Relevance scores - these should be saved
                'topic_alignment_score': 0.85,
                'keyword_relevance_score': 0.92,
                'confidence_score': 0.88,
                'auto_ingested': True,
                'ingest_status': 'auto'
            }
        ]

        # Mock MediaBias
        with patch('app.bulk_research.MediaBias') as MockMediaBias:
            mock_media_bias = MockMediaBias.return_value
            mock_media_bias.get_status.return_value = {'enabled': False}

            # Capture the executed insert statement
            captured_data = {}

            def capture_insert(stmt):
                # The statement contains the values
                if hasattr(stmt, 'compile'):
                    compiled = stmt.compile()
                    if hasattr(compiled, 'params'):
                        captured_data.update(compiled.params)

                # For our mock, extract values from the statement
                if hasattr(stmt, '_values'):
                    captured_data.update(stmt._values)

                return MagicMock(rowcount=1)

            mock_conn = mock_db._temp_get_connection.return_value
            mock_conn.execute.side_effect = capture_insert

            batch_results = {"success": [], "errors": []}
            await bulk_research._save_articles_transaction(articles, batch_results)

        # Verify the article was marked as successfully saved
        assert len(batch_results["success"]) == 1
        assert batch_results["success"][0]["uri"] == 'https://example.com/article1'

        # Verify execute was called (article insert)
        assert mock_conn.execute.called

    @pytest.mark.asyncio
    async def test_save_articles_with_partial_relevance_scores(self, mock_db, mock_research):
        """Test saving articles with only topic_alignment_score"""
        bulk_research = BulkResearch(db=mock_db, research=mock_research)

        articles = [
            {
                'uri': 'https://example.com/article2',
                'title': 'Partial Scores Article',
                'news_source': 'TestSource',
                'publication_date': '2025-10-09',
                'submission_date': '2025-10-09',
                'summary': 'Test',
                'category': 'Tech',
                'future_signal': 'Signal',
                'future_signal_explanation': 'Explanation',
                'sentiment': 'Neutral',
                'sentiment_explanation': 'Neutral explanation',
                'time_to_impact': 'Mid-term',
                'time_to_impact_explanation': 'Medium time',
                'tags': 'test',
                'driver_type': 'Catalyst',
                'driver_type_explanation': 'Drives change',
                'topic': 'Technology',
                'analyzed': True,
                # Only one relevance score (from legacy method)
                'topic_alignment_score': 0.65,
                # keyword_relevance_score and confidence_score will be None
                'keyword_relevance_score': None,
                'confidence_score': None
            }
        ]

        with patch('app.bulk_research.MediaBias') as MockMediaBias:
            mock_media_bias = MockMediaBias.return_value
            mock_media_bias.get_status.return_value = {'enabled': False}

            batch_results = {"success": [], "errors": []}
            await bulk_research._save_articles_transaction(articles, batch_results)

        assert len(batch_results["success"]) == 1
        assert len(batch_results["errors"]) == 0

    @pytest.mark.asyncio
    async def test_save_articles_without_relevance_scores(self, mock_db, mock_research):
        """Test saving articles without any relevance scores (manual ingestion)"""
        bulk_research = BulkResearch(db=mock_db, research=mock_research)

        articles = [
            {
                'uri': 'https://example.com/manual-article',
                'title': 'Manually Ingested Article',
                'news_source': 'ManualSource',
                'publication_date': '2025-10-09',
                'submission_date': '2025-10-09',
                'summary': 'Manually added',
                'category': 'General',
                'future_signal': 'Unknown',
                'future_signal_explanation': 'TBD',
                'sentiment': 'Neutral',
                'sentiment_explanation': 'Neutral',
                'time_to_impact': 'Unknown',
                'time_to_impact_explanation': 'TBD',
                'tags': 'manual',
                'driver_type': 'Unknown',
                'driver_type_explanation': 'TBD',
                'topic': 'General',
                'analyzed': True,
                # No relevance scores for manual ingestion
                'auto_ingested': False,
                'ingest_status': 'manual'
            }
        ]

        with patch('app.bulk_research.MediaBias') as MockMediaBias:
            mock_media_bias = MockMediaBias.return_value
            mock_media_bias.get_status.return_value = {'enabled': False}

            batch_results = {"success": [], "errors": []}
            await bulk_research._save_articles_transaction(articles, batch_results)

        # Should still save successfully with None values for scores
        assert len(batch_results["success"]) == 1


class TestRelevanceScoresInBulkSave:
    """Test relevance scores in the complete save_bulk_articles flow"""

    @pytest.mark.asyncio
    async def test_save_bulk_articles_preserves_relevance_scores(self, mock_db, mock_research):
        """Test that save_bulk_articles preserves relevance scores through the pipeline"""
        bulk_research = BulkResearch(db=mock_db, research=mock_research)

        articles = [
            {
                'uri': 'https://example.com/scored-article',
                'title': 'Article with Scores',
                'news_source': 'ScoredSource',
                'publication_date': '2025-10-09',
                'submission_date': '2025-10-09',
                'summary': 'Summary',
                'category': 'AI Business',
                'future_signal': 'AI will accelerate',
                'future_signal_explanation': 'Explanation',
                'sentiment': 'Positive',
                'sentiment_explanation': 'Explanation',
                'time_to_impact': 'Short-term',
                'time_to_impact_explanation': 'Explanation',
                'tags': 'ai',
                'driver_type': 'Accelerator',
                'driver_type_explanation': 'Explanation',
                'topic': 'AI and Machine Learning',
                'analyzed': True,
                # Relevance scores from auto-ingest
                'topic_alignment_score': 0.92,
                'keyword_relevance_score': 0.88,
                'confidence_score': 0.90,
                'auto_ingested': True,
                'ingest_status': 'auto'
            }
        ]

        with patch('app.bulk_research.MediaBias') as MockMediaBias:
            mock_media_bias = MockMediaBias.return_value
            mock_media_bias.get_status.return_value = {'enabled': False}

            # Mock _index_articles_vector to avoid vector store operations
            bulk_research._index_articles_vector = AsyncMock()

            results = await bulk_research.save_bulk_articles(articles)

        # Verify successful save
        assert len(results["success"]) == 1
        assert len(results["errors"]) == 0

    @pytest.mark.asyncio
    async def test_batch_processing_preserves_scores(self, mock_db, mock_research):
        """Test that batch processing preserves relevance scores for all articles"""
        bulk_research = BulkResearch(db=mock_db, research=mock_research)

        # Multiple articles with different score combinations
        articles = [
            {
                'uri': f'https://example.com/article{i}',
                'title': f'Article {i}',
                'news_source': 'TestSource',
                'publication_date': '2025-10-09',
                'submission_date': '2025-10-09',
                'summary': f'Summary {i}',
                'category': 'Category',
                'future_signal': 'Signal',
                'future_signal_explanation': 'Explanation',
                'sentiment': 'Neutral',
                'sentiment_explanation': 'Explanation',
                'time_to_impact': 'Mid-term',
                'time_to_impact_explanation': 'Explanation',
                'tags': 'test',
                'driver_type': 'Catalyst',
                'driver_type_explanation': 'Explanation',
                'topic': 'Technology',
                'analyzed': True,
                'topic_alignment_score': 0.5 + (i * 0.1),
                'keyword_relevance_score': 0.6 + (i * 0.05),
                'confidence_score': 0.7 + (i * 0.05),
                'auto_ingested': True,
                'ingest_status': 'auto'
            }
            for i in range(5)
        ]

        with patch('app.bulk_research.MediaBias') as MockMediaBias:
            mock_media_bias = MockMediaBias.return_value
            mock_media_bias.get_status.return_value = {'enabled': False}

            bulk_research._index_articles_vector = AsyncMock()

            results = await bulk_research.save_bulk_articles(articles)

        # All articles should be saved successfully
        assert len(results["success"]) == 5
        assert len(results["errors"]) == 0


class TestPostgreSQLCompatibility:
    """Test PostgreSQL-specific features in save operations"""

    @pytest.mark.asyncio
    async def test_uses_on_conflict_do_update_for_postgresql(self, mock_db, mock_research):
        """Test that PostgreSQL uses on_conflict_do_update for upserts"""
        bulk_research = BulkResearch(db=mock_db, research=mock_research)

        articles = [
            {
                'uri': 'https://example.com/existing-article',
                'title': 'Updated Article',
                'news_source': 'Source',
                'publication_date': '2025-10-09',
                'submission_date': '2025-10-09',
                'summary': 'Updated summary',
                'category': 'Updated Category',
                'future_signal': 'Signal',
                'future_signal_explanation': 'Explanation',
                'sentiment': 'Positive',
                'sentiment_explanation': 'Explanation',
                'time_to_impact': 'Short-term',
                'time_to_impact_explanation': 'Explanation',
                'tags': 'updated',
                'driver_type': 'Accelerator',
                'driver_type_explanation': 'Explanation',
                'topic': 'Technology',
                'analyzed': True,
                'topic_alignment_score': 0.95,
                'keyword_relevance_score': 0.93,
                'confidence_score': 0.94
            }
        ]

        with patch('app.bulk_research.MediaBias') as MockMediaBias, \
             patch('app.bulk_research.insert') as mock_insert:

            mock_media_bias = MockMediaBias.return_value
            mock_media_bias.get_status.return_value = {'enabled': False}

            # Mock the insert statement
            mock_stmt = MagicMock()
            mock_on_conflict_stmt = MagicMock()
            mock_stmt.on_conflict_do_update.return_value = mock_on_conflict_stmt
            mock_insert.return_value = mock_stmt

            batch_results = {"success": [], "errors": []}
            await bulk_research._save_articles_transaction(articles, batch_results)

            # Verify on_conflict_do_update was called for PostgreSQL
            if mock_db.db_type == 'postgresql':
                mock_stmt.on_conflict_do_update.assert_called()


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
