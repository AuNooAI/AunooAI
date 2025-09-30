#!/usr/bin/env python3
"""
Test suite for future_signal validation system.

Tests three layers of protection:
1. ArticleAnalyzer validation rejects invalid AI outputs
2. Database query filtering returns only valid signals
3. Integration test ensures end-to-end validation works
"""

import sys
import os
import unittest
from unittest.mock import Mock, MagicMock, patch
import logging

# Add app directory to path
sys.path.insert(0, os.path.abspath('.'))

from app.analyzers.article_analyzer import ArticleAnalyzer
from app.database import Database
from app.database_query_facade import DatabaseQueryFacade
from app.config.settings import load_config

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class TestFutureSignalValidation(unittest.TestCase):
    """Test validation of future_signal values against topic ontology"""

    def setUp(self):
        """Set up test fixtures"""
        # Load actual config to get real ontology
        self.config = load_config()

        # Get AI and Machine Learning topic ontology
        self.ai_topic = next(
            (topic for topic in self.config['topics']
             if topic['name'] == 'AI and Machine Learning'),
            None
        )

        self.assertIsNotNone(self.ai_topic, "AI and Machine Learning topic not found in config")

        # Valid and invalid signals for testing
        self.valid_signals = self.ai_topic['future_signals']
        self.valid_sentiments = self.ai_topic['sentiment']
        self.valid_time_to_impact = self.ai_topic['time_to_impact']
        self.valid_categories = self.ai_topic['categories']
        self.valid_driver_types = self.ai_topic['driver_types']

        # Invalid signals that AI might hallucinate
        self.invalid_signals = [
            "Acceleration",  # Shortened version
            "Gradual Evolution",  # Shortened version
            "Hype",  # Shortened version
            "Neutral",  # Sentiment value
            "Positive",  # Sentiment value
            "None",  # Null value
            "N/A",  # Null value
            "Not applicable",  # Null value
            "Short-term (6-18 months)",  # Time to impact value
            "Immediate",  # Time to impact value
            "Economic Impacts",  # Random garbage
            "Mixed",  # Sentiment value
        ]

    def test_valid_signals_pass_validation(self):
        """Test that valid future_signals are accepted"""
        # Create mock AI model
        mock_ai_model = Mock()
        mock_ai_model.model_name = "test-model"

        # Create ArticleAnalyzer
        analyzer = ArticleAnalyzer(mock_ai_model, use_cache=False)

        # Test each valid signal
        for valid_signal in self.valid_signals:
            result = {
                'future_signal': valid_signal,
                'sentiment': 'Positive',
                'time_to_impact': 'Short-term (6-18 months)',
                'category': 'Other',
                'driver_type': self.valid_driver_types[0]  # Use actual valid driver type
            }

            validated = analyzer._validate_analysis_fields(
                result,
                self.valid_categories,
                self.valid_signals,
                self.valid_sentiments,
                self.valid_time_to_impact,
                self.valid_driver_types
            )

            self.assertEqual(
                validated['future_signal'],
                valid_signal,
                f"Valid signal '{valid_signal}' should not be modified"
            )

    def test_invalid_signals_rejected(self):
        """Test that invalid future_signals are rejected and cleared"""
        # Create mock AI model
        mock_ai_model = Mock()
        mock_ai_model.model_name = "test-model"

        # Create ArticleAnalyzer
        analyzer = ArticleAnalyzer(mock_ai_model, use_cache=False)

        # Test each invalid signal
        for invalid_signal in self.invalid_signals:
            result = {
                'future_signal': invalid_signal,
                'future_signal_explanation': 'Original explanation',
                'sentiment': 'Positive',
                'time_to_impact': 'Short-term (6-18 months)',
                'category': 'Other',
                'driver_type': self.valid_driver_types[0]
            }

            validated = analyzer._validate_analysis_fields(
                result,
                self.valid_categories,
                self.valid_signals,
                self.valid_sentiments,
                self.valid_time_to_impact,
                self.valid_driver_types
            )

            self.assertEqual(
                validated['future_signal'],
                "",
                f"Invalid signal '{invalid_signal}' should be cleared to empty string"
            )

            self.assertIn(
                "VALIDATION ERROR",
                validated.get('future_signal_explanation', ''),
                f"Invalid signal '{invalid_signal}' should have validation error in explanation"
            )

    def test_sentiment_validation(self):
        """Test that invalid sentiment values are rejected"""
        mock_ai_model = Mock()
        mock_ai_model.model_name = "test-model"
        analyzer = ArticleAnalyzer(mock_ai_model, use_cache=False)

        invalid_sentiments = ["Happy", "Sad", "Excited", "None", "N/A"]

        for invalid_sentiment in invalid_sentiments:
            result = {
                'future_signal': 'AI will accelerate',
                'sentiment': invalid_sentiment,
                'time_to_impact': 'Short-term (6-18 months)',
                'category': 'Other',
                'driver_type': self.valid_driver_types[0]
            }

            validated = analyzer._validate_analysis_fields(
                result,
                self.valid_categories,
                self.valid_signals,
                self.valid_sentiments,
                self.valid_time_to_impact,
                self.valid_driver_types
            )

            self.assertEqual(
                validated['sentiment'],
                "",
                f"Invalid sentiment '{invalid_sentiment}' should be cleared"
            )

    def test_time_to_impact_validation(self):
        """Test that invalid time_to_impact values are rejected"""
        mock_ai_model = Mock()
        mock_ai_model.model_name = "test-model"
        analyzer = ArticleAnalyzer(mock_ai_model, use_cache=False)

        invalid_times = ["Soon", "Later", "Never", "None", "Short-term (6-18 months)"]

        for invalid_time in invalid_times:
            result = {
                'future_signal': 'AI will accelerate',
                'sentiment': 'Positive',
                'time_to_impact': invalid_time,
                'category': 'Other',
                'driver_type': self.valid_driver_types[0]
            }

            validated = analyzer._validate_analysis_fields(
                result,
                self.valid_categories,
                self.valid_signals,
                self.valid_sentiments,
                self.valid_time_to_impact,
                self.valid_driver_types
            )

            self.assertEqual(
                validated['time_to_impact'],
                "",
                f"Invalid time_to_impact '{invalid_time}' should be cleared"
            )

    def test_empty_values_allowed(self):
        """Test that empty/missing values are allowed (not validated)"""
        mock_ai_model = Mock()
        mock_ai_model.model_name = "test-model"
        analyzer = ArticleAnalyzer(mock_ai_model, use_cache=False)

        result = {
            'future_signal': '',
            'sentiment': '',
            'time_to_impact': '',
            'category': '',
            'driver_type': ''
        }

        validated = analyzer._validate_analysis_fields(
            result,
            self.valid_categories,
            self.valid_signals,
            self.valid_sentiments,
            self.valid_time_to_impact,
            self.valid_driver_types
        )

        # Empty values should pass through unchanged
        self.assertEqual(validated['future_signal'], '')
        self.assertEqual(validated['sentiment'], '')
        self.assertEqual(validated['time_to_impact'], '')

    @patch('app.config.settings.load_config')
    def test_database_query_filtering(self, mock_load_config):
        """Test that database queries filter by ontology"""
        # Mock the config
        mock_load_config.return_value = self.config

        # Create a mock database
        mock_db = Mock(spec=Database)

        # Mock the fetch_all to return mixed valid/invalid signals
        mock_db.fetch_all.return_value = [
            ('AI will accelerate', 100),  # Valid
            ('Acceleration', 50),  # Invalid (shortened)
            ('AI is hype', 30),  # Valid
            ('Neutral', 20),  # Invalid (sentiment)
            ('AI has plateaued', 10),  # Valid
        ]

        # Create facade
        facade = DatabaseQueryFacade(mock_db, logger)

        # Call the method
        results = facade.get_topic_filtered_future_signals_with_counts_for_market_signal_analysis(
            'AI and Machine Learning'
        )

        # Verify the SQL query was called with correct parameters
        self.assertTrue(mock_db.fetch_all.called)

        # Get the actual SQL and params used
        call_args = mock_db.fetch_all.call_args
        sql_query = call_args[0][0]
        params = call_args[0][1]

        # Verify SQL contains IN clause with placeholders
        self.assertIn('IN (', sql_query)
        self.assertIn('future_signal', sql_query)

        # Verify parameters include topic name and valid signals
        self.assertEqual(params[0], 'AI and Machine Learning')
        self.assertIn('AI will accelerate', params)
        self.assertIn('AI is hype', params)
        self.assertIn('AI has plateaued', params)

    def test_mixed_valid_invalid_signals(self):
        """Test validation with mix of valid and invalid fields"""
        mock_ai_model = Mock()
        mock_ai_model.model_name = "test-model"
        analyzer = ArticleAnalyzer(mock_ai_model, use_cache=False)

        # AI returns mix of valid and invalid
        result = {
            'future_signal': 'Acceleration',  # Invalid
            'future_signal_explanation': 'Original explanation',
            'sentiment': 'Positive',  # Valid
            'time_to_impact': 'Soon',  # Invalid
            'category': 'AI Business',  # Valid
            'driver_type': self.valid_driver_types[0]  # Valid
        }

        validated = analyzer._validate_analysis_fields(
            result,
            self.valid_categories,
            self.valid_signals,
            self.valid_sentiments,
            self.valid_time_to_impact,
            self.valid_driver_types
        )

        # Invalid fields should be cleared
        self.assertEqual(validated['future_signal'], "")
        self.assertEqual(validated['time_to_impact'], "")

        # Valid fields should be preserved
        self.assertEqual(validated['sentiment'], "Positive")
        self.assertEqual(validated['category'], "AI Business")
        self.assertEqual(validated['driver_type'], self.valid_driver_types[0])

    def test_climate_change_topic_validation(self):
        """Test validation works for different topic (Climate Change)"""
        # Get Climate Change topic
        climate_topic = next(
            (topic for topic in self.config['topics']
             if topic['name'] == 'Climate Change'),
            None
        )

        if not climate_topic:
            self.skipTest("Climate Change topic not found in config")

        mock_ai_model = Mock()
        mock_ai_model.model_name = "test-model"
        analyzer = ArticleAnalyzer(mock_ai_model, use_cache=False)

        # Test valid signal for Climate Change
        result = {
            'future_signal': 'Failure to meet emission targets',  # Valid for Climate Change
            'sentiment': 'Negative',
            'time_to_impact': climate_topic['time_to_impact'][0],  # Use actual valid value
            'category': 'Other',
            'driver_type': climate_topic['driver_types'][0]  # Use actual valid value
        }

        validated = analyzer._validate_analysis_fields(
            result,
            climate_topic['categories'],
            climate_topic['future_signals'],
            climate_topic['sentiment'],
            climate_topic['time_to_impact'],
            climate_topic['driver_types']
        )

        self.assertEqual(
            validated['future_signal'],
            'Failure to meet emission targets',
            "Valid Climate Change signal should be preserved"
        )

        # Test that AI topic signal is invalid for Climate Change topic
        result_invalid = {
            'future_signal': 'AI will accelerate',  # Valid for AI, invalid for Climate
            'sentiment': 'Neutral',
            'time_to_impact': climate_topic['time_to_impact'][0],
            'category': 'Other',
            'driver_type': climate_topic['driver_types'][0]
        }

        validated_invalid = analyzer._validate_analysis_fields(
            result_invalid,
            climate_topic['categories'],
            climate_topic['future_signals'],
            climate_topic['sentiment'],
            climate_topic['time_to_impact'],
            climate_topic['driver_types']
        )

        self.assertEqual(
            validated_invalid['future_signal'],
            "",
            "AI signal should be invalid for Climate Change topic"
        )


class TestIntegration(unittest.TestCase):
    """Integration tests for the complete validation pipeline"""

    def test_end_to_end_validation(self):
        """Test that validation works in a realistic scenario"""
        config = load_config()
        ai_topic = next(
            (topic for topic in config['topics']
             if topic['name'] == 'AI and Machine Learning'),
            None
        )

        self.assertIsNotNone(ai_topic)

        # Simulate AI returning various invalid values
        test_cases = [
            {
                'input': 'Acceleration',
                'expected_output': '',
                'description': 'Shortened future signal'
            },
            {
                'input': 'AI will accelerate',
                'expected_output': 'AI will accelerate',
                'description': 'Valid future signal'
            },
            {
                'input': 'Neutral',
                'expected_output': '',
                'description': 'Sentiment value in future_signal field'
            },
            {
                'input': 'None',
                'expected_output': '',
                'description': 'Null placeholder'
            }
        ]

        mock_ai_model = Mock()
        mock_ai_model.model_name = "test-model"
        analyzer = ArticleAnalyzer(mock_ai_model, use_cache=False)

        for test_case in test_cases:
            result = {
                'future_signal': test_case['input'],
                'future_signal_explanation': 'Test explanation',
                'sentiment': 'Positive',
                'time_to_impact': ai_topic['time_to_impact'][0],
                'category': 'AI Business',
                'driver_type': ai_topic['driver_types'][0]
            }

            validated = analyzer._validate_analysis_fields(
                result,
                ai_topic['categories'],
                ai_topic['future_signals'],
                ai_topic['sentiment'],
                ai_topic['time_to_impact'],
                ai_topic['driver_types']
            )

            self.assertEqual(
                validated['future_signal'],
                test_case['expected_output'],
                f"Failed for test case: {test_case['description']}"
            )


def run_tests():
    """Run all tests"""
    # Create test suite
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()

    # Add all test classes
    suite.addTests(loader.loadTestsFromTestCase(TestFutureSignalValidation))
    suite.addTests(loader.loadTestsFromTestCase(TestIntegration))

    # Run tests with verbose output
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    # Print summary
    print("\n" + "="*70)
    print("TEST SUMMARY")
    print("="*70)
    print(f"Tests run: {result.testsRun}")
    print(f"Successes: {result.testsRun - len(result.failures) - len(result.errors)}")
    print(f"Failures: {len(result.failures)}")
    print(f"Errors: {len(result.errors)}")
    print("="*70)

    return result.wasSuccessful()


if __name__ == '__main__':
    success = run_tests()
    sys.exit(0 if success else 1)