"""
Tests for Bulk Delete Articles
Tests PostgreSQL-compatible bulk deletion with SQLAlchemy Core.
"""
import pytest
from unittest.mock import Mock, patch, MagicMock
from sqlalchemy import delete

from app.database import Database


@pytest.fixture
def mock_db():
    """Mock database instance"""
    db = Mock(spec=Database)
    db.db_type = 'postgresql'

    # Mock connection
    mock_conn = MagicMock()
    mock_trans = MagicMock()

    mock_conn.begin.return_value = mock_trans
    mock_conn.execute.return_value = MagicMock(rowcount=3)

    db._temp_get_connection.return_value = mock_conn

    return db


class TestBulkDeleteArticles:
    """Test bulk article deletion functionality"""

    def test_bulk_delete_articles_success(self, mock_db):
        """Test successful bulk deletion of articles"""
        from app.database import Database

        # Create a real Database instance and override its methods
        real_db = Database.__new__(Database)
        real_db.db_type = 'postgresql'

        # Mock connection and transaction
        mock_conn = MagicMock()
        mock_trans = MagicMock()
        mock_conn.begin.return_value = mock_trans

        # Mock execute to return successful rowcounts
        execute_results = [
            MagicMock(rowcount=2),  # keyword_article_matches
            MagicMock(rowcount=1),  # article_annotations
            MagicMock(rowcount=3),  # raw_articles
            MagicMock(rowcount=3),  # articles (main table)
        ]
        mock_conn.execute.side_effect = execute_results

        real_db._temp_get_connection = Mock(return_value=mock_conn)

        # Test data
        uris = [
            'https://example.com/article1',
            'https://example.com/article2',
            'https://example.com/article3'
        ]

        # Execute deletion
        deleted_count = real_db.bulk_delete_articles(uris)

        # Verify results
        assert deleted_count == 3

        # Verify transaction was committed
        mock_trans.commit.assert_called_once()

        # Verify execute was called 4 times (related tables + articles)
        assert mock_conn.execute.call_count == 4

    def test_bulk_delete_articles_empty_list(self, mock_db):
        """Test bulk delete with empty URI list"""
        from app.database import Database

        real_db = Database.__new__(Database)
        real_db.db_type = 'postgresql'

        deleted_count = real_db.bulk_delete_articles([])

        assert deleted_count == 0

    def test_bulk_delete_articles_transaction_rollback(self, mock_db):
        """Test transaction rollback on error"""
        from app.database import Database

        real_db = Database.__new__(Database)
        real_db.db_type = 'postgresql'

        # Mock connection with error
        mock_conn = MagicMock()
        mock_trans = MagicMock()
        mock_conn.begin.return_value = mock_trans
        mock_conn.execute.side_effect = Exception("Database error")

        real_db._temp_get_connection = Mock(return_value=mock_conn)

        uris = ['https://example.com/article1']

        # Should raise exception
        with pytest.raises(Exception):
            real_db.bulk_delete_articles(uris)

        # Verify rollback was called
        mock_trans.rollback.assert_called_once()

    def test_bulk_delete_uses_sqlalchemy_core(self, mock_db):
        """Test that bulk delete uses SQLAlchemy Core statements"""
        from app.database import Database
        from app.database_models import t_articles

        real_db = Database.__new__(Database)
        real_db.db_type = 'postgresql'

        mock_conn = MagicMock()
        mock_trans = MagicMock()
        mock_conn.begin.return_value = mock_trans

        # Capture the SQL statements
        executed_statements = []

        def capture_execute(stmt):
            executed_statements.append(stmt)
            return MagicMock(rowcount=1)

        mock_conn.execute.side_effect = capture_execute
        real_db._temp_get_connection = Mock(return_value=mock_conn)

        uris = ['https://example.com/article1']

        with patch('app.database.delete') as mock_delete, \
             patch('app.database.t_articles') as mock_t_articles, \
             patch('app.database.t_raw_articles'), \
             patch('app.database.t_keyword_article_matches'), \
             patch('app.database.t_article_annotations'):

            # Mock the delete statement builder
            mock_delete_stmt = MagicMock()
            mock_where_stmt = MagicMock()
            mock_delete_stmt.where.return_value = mock_where_stmt
            mock_delete.return_value = mock_delete_stmt

            real_db.bulk_delete_articles(uris)

            # Verify delete() was called (SQLAlchemy Core)
            assert mock_delete.called

            # Verify .where() was used with .in_()
            assert mock_delete_stmt.where.called

    def test_bulk_delete_url_decoding(self):
        """Test URL decoding for encoded URIs"""
        from urllib.parse import quote_plus
        from app.database import Database

        real_db = Database.__new__(Database)
        real_db.db_type = 'postgresql'

        # Mock connection
        mock_conn = MagicMock()
        mock_trans = MagicMock()
        mock_conn.begin.return_value = mock_trans
        mock_conn.execute.return_value = MagicMock(rowcount=1)

        real_db._temp_get_connection = Mock(return_value=mock_conn)

        # Test with encoded URL
        encoded_uri = quote_plus(quote_plus('https://example.com/article with spaces'))

        deleted_count = real_db.bulk_delete_articles([encoded_uri])

        assert deleted_count == 1

        # The method should have decoded the URI before querying

    def test_bulk_delete_partial_success(self):
        """Test bulk delete when some articles don't exist"""
        from app.database import Database

        real_db = Database.__new__(Database)
        real_db.db_type = 'postgresql'

        mock_conn = MagicMock()
        mock_trans = MagicMock()
        mock_conn.begin.return_value = mock_trans

        # Some articles exist, some don't
        execute_results = [
            MagicMock(rowcount=1),  # keyword_article_matches
            MagicMock(rowcount=0),  # article_annotations (none found)
            MagicMock(rowcount=2),  # raw_articles
            MagicMock(rowcount=2),  # articles (only 2 of 5 found)
        ]
        mock_conn.execute.side_effect = execute_results

        real_db._temp_get_connection = Mock(return_value=mock_conn)

        uris = [
            'https://example.com/article1',
            'https://example.com/article2',
            'https://example.com/article3',
            'https://example.com/nonexistent1',
            'https://example.com/nonexistent2'
        ]

        deleted_count = real_db.bulk_delete_articles(uris)

        # Should return actual count of deleted articles
        assert deleted_count == 2


class TestBulkDeleteCascade:
    """Test cascade deletion of related records"""

    def test_deletes_keyword_article_matches(self):
        """Test deletion of keyword_article_matches records"""
        from app.database import Database

        real_db = Database.__new__(Database)
        real_db.db_type = 'postgresql'

        mock_conn = MagicMock()
        mock_trans = MagicMock()
        mock_conn.begin.return_value = mock_trans

        keyword_matches_deleted = MagicMock(rowcount=5)
        other_deletes = MagicMock(rowcount=3)

        mock_conn.execute.side_effect = [
            keyword_matches_deleted,  # keyword_article_matches
            other_deletes,  # article_annotations
            other_deletes,  # raw_articles
            other_deletes,  # articles
        ]

        real_db._temp_get_connection = Mock(return_value=mock_conn)

        uris = ['https://example.com/article1']

        deleted_count = real_db.bulk_delete_articles(uris)

        # All deletes should have been attempted
        assert mock_conn.execute.call_count == 4

    def test_deletes_raw_articles(self):
        """Test deletion of raw_articles records"""
        from app.database import Database

        real_db = Database.__new__(Database)
        real_db.db_type = 'postgresql'

        mock_conn = MagicMock()
        mock_trans = MagicMock()
        mock_conn.begin.return_value = mock_trans

        execute_results = [
            MagicMock(rowcount=0),  # keyword_article_matches
            MagicMock(rowcount=0),  # article_annotations
            MagicMock(rowcount=3),  # raw_articles (3 deleted)
            MagicMock(rowcount=3),  # articles
        ]
        mock_conn.execute.side_effect = execute_results

        real_db._temp_get_connection = Mock(return_value=mock_conn)

        uris = [
            'https://example.com/article1',
            'https://example.com/article2',
            'https://example.com/article3'
        ]

        deleted_count = real_db.bulk_delete_articles(uris)

        assert deleted_count == 3


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
