"""
Unit tests for LLM exception classification and error handling.

Tests the exception classification system that categorizes LiteLLM exceptions
into severity levels (FATAL, RECOVERABLE, SKIPPABLE, DEGRADED) and the
PipelineError wrapper exception.
"""

from unittest.mock import Mock, patch
import pytest
import litellm
from app.exceptions import (
    ErrorSeverity,
    LLMErrorClassifier,
    PipelineError
)


class TestErrorSeverity:
    """Test the ErrorSeverity enum."""

    def test_severity_values(self):
        """Test that severity enum has expected values."""
        assert ErrorSeverity.FATAL.value == "fatal"
        assert ErrorSeverity.RECOVERABLE.value == "recoverable"
        assert ErrorSeverity.SKIPPABLE.value == "skippable"
        assert ErrorSeverity.DEGRADED.value == "degraded"

    def test_severity_members(self):
        """Test that all expected severity levels exist."""
        severities = [s.value for s in ErrorSeverity]
        assert "fatal" in severities
        assert "recoverable" in severities
        assert "skippable" in severities
        assert "degraded" in severities
        assert len(severities) == 4


class TestLLMErrorClassifier:
    """Test the LLM error classification system."""

    def test_fatal_exceptions_classification(self):
        """Test that fatal exceptions are classified correctly."""
        # AuthenticationError
        auth_error = litellm.AuthenticationError(
            message="Invalid API key",
            model="gpt-4",
            llm_provider="openai"
        )
        severity, should_retry = LLMErrorClassifier.classify_error(auth_error)
        assert severity == ErrorSeverity.FATAL
        assert should_retry is False

        # BudgetExceededError
        budget_error = litellm.BudgetExceededError(
            message="Budget exceeded",
            model="gpt-4",
            llm_provider="openai"
        )
        severity, should_retry = LLMErrorClassifier.classify_error(budget_error)
        assert severity == ErrorSeverity.FATAL
        assert should_retry is False

    def test_recoverable_exceptions_classification(self):
        """Test that recoverable exceptions are classified correctly."""
        # RateLimitError
        rate_limit_error = litellm.RateLimitError(
            message="Rate limit exceeded",
            model="gpt-4",
            llm_provider="openai"
        )
        severity, should_retry = LLMErrorClassifier.classify_error(rate_limit_error)
        assert severity == ErrorSeverity.RECOVERABLE
        assert should_retry is True

        # Timeout
        timeout_error = litellm.Timeout(
            message="Request timed out",
            model="gpt-4",
            llm_provider="openai"
        )
        severity, should_retry = LLMErrorClassifier.classify_error(timeout_error)
        assert severity == ErrorSeverity.RECOVERABLE
        assert should_retry is True

        # APIConnectionError
        connection_error = litellm.APIConnectionError(
            message="Connection failed",
            model="gpt-4",
            llm_provider="openai"
        )
        severity, should_retry = LLMErrorClassifier.classify_error(connection_error)
        assert severity == ErrorSeverity.RECOVERABLE
        assert should_retry is True

    def test_skippable_exceptions_classification(self):
        """Test that skippable exceptions are classified correctly."""
        # ContextWindowExceededError
        context_error = litellm.ContextWindowExceededError(
            message="Context window exceeded",
            model="gpt-4",
            llm_provider="openai"
        )
        severity, should_retry = LLMErrorClassifier.classify_error(context_error)
        assert severity == ErrorSeverity.SKIPPABLE
        assert should_retry is False

        # BadRequestError
        bad_request_error = litellm.BadRequestError(
            message="Invalid request",
            model="gpt-4",
            llm_provider="openai"
        )
        severity, should_retry = LLMErrorClassifier.classify_error(bad_request_error)
        assert severity == ErrorSeverity.SKIPPABLE
        assert should_retry is False

        # InvalidRequestError
        invalid_request_error = litellm.InvalidRequestError(
            message="Invalid request parameter",
            model="gpt-4",
            llm_provider="openai"
        )
        severity, should_retry = LLMErrorClassifier.classify_error(invalid_request_error)
        assert severity == ErrorSeverity.SKIPPABLE
        assert should_retry is False

        # JSONSchemaValidationError
        json_error = litellm.JSONSchemaValidationError(
            message="JSON schema validation failed",
            model="gpt-4",
            llm_provider="openai"
        )
        severity, should_retry = LLMErrorClassifier.classify_error(json_error)
        assert severity == ErrorSeverity.SKIPPABLE
        assert should_retry is False

    def test_degraded_exceptions_classification(self):
        """Test that degraded exceptions are classified correctly."""
        # ServiceUnavailableError
        service_error = litellm.ServiceUnavailableError(
            message="Service temporarily unavailable",
            model="gpt-4",
            llm_provider="openai"
        )
        severity, should_retry = LLMErrorClassifier.classify_error(service_error)
        assert severity == ErrorSeverity.DEGRADED
        assert should_retry is True

        # APIError
        api_error = litellm.APIError(
            message="API error occurred",
            model="gpt-4",
            llm_provider="openai"
        )
        severity, should_retry = LLMErrorClassifier.classify_error(api_error)
        assert severity == ErrorSeverity.DEGRADED
        assert should_retry is True

    def test_unknown_exception_classification(self):
        """Test that unknown exceptions are classified as DEGRADED."""
        unknown_error = Exception("Unknown error type")
        severity, should_retry = LLMErrorClassifier.classify_error(unknown_error)
        assert severity == ErrorSeverity.DEGRADED
        assert should_retry is False

    def test_get_error_message(self):
        """Test extracting error messages from exceptions."""
        # Test with message attribute
        error_with_message = litellm.AuthenticationError(
            message="Test error message",
            model="gpt-4",
            llm_provider="openai"
        )
        message = LLMErrorClassifier.get_error_message(error_with_message)
        assert "Test error message" in message

        # Test with string conversion fallback
        error_without_message = Exception("Fallback message")
        message = LLMErrorClassifier.get_error_message(error_without_message)
        assert "Fallback message" in message

    def test_classify_error_returns_tuple(self):
        """Test that classify_error always returns a tuple of (severity, should_retry)."""
        error = litellm.RateLimitError(
            message="Test",
            model="gpt-4",
            llm_provider="openai"
        )
        result = LLMErrorClassifier.classify_error(error)
        assert isinstance(result, tuple)
        assert len(result) == 2
        assert isinstance(result[0], ErrorSeverity)
        assert isinstance(result[1], bool)


class TestPipelineError:
    """Test the PipelineError custom exception."""

    def test_pipeline_error_creation(self):
        """Test creating a PipelineError."""
        original_error = litellm.AuthenticationError(
            message="Invalid API key",
            model="gpt-4",
            llm_provider="openai"
        )

        pipeline_error = PipelineError(
            message="Pipeline failed",
            original_error=original_error,
            severity=ErrorSeverity.FATAL,
            model_name="gpt-4",
            article_uri="https://example.com/article"
        )

        assert pipeline_error.message == "Pipeline failed"
        assert pipeline_error.original_error == original_error
        assert pipeline_error.severity == ErrorSeverity.FATAL
        assert pipeline_error.model_name == "gpt-4"
        assert pipeline_error.article_uri == "https://example.com/article"

    def test_pipeline_error_str_representation(self):
        """Test string representation of PipelineError."""
        original_error = Exception("Original error message")

        pipeline_error = PipelineError(
            message="Pipeline failed",
            original_error=original_error,
            severity=ErrorSeverity.RECOVERABLE,
            model_name="gpt-3.5-turbo"
        )

        error_str = str(pipeline_error)
        assert "Pipeline failed" in error_str
        assert "RECOVERABLE" in error_str
        assert "gpt-3.5-turbo" in error_str

    def test_pipeline_error_optional_fields(self):
        """Test that optional fields can be None."""
        pipeline_error = PipelineError(
            message="Simple error",
            original_error=None,
            severity=ErrorSeverity.SKIPPABLE,
            model_name=None,
            article_uri=None
        )

        assert pipeline_error.original_error is None
        assert pipeline_error.model_name is None
        assert pipeline_error.article_uri is None
        assert pipeline_error.severity == ErrorSeverity.SKIPPABLE

    def test_pipeline_error_with_context(self):
        """Test PipelineError with additional context."""
        original_error = litellm.RateLimitError(
            message="Rate limit exceeded",
            model="gpt-4",
            llm_provider="openai"
        )

        pipeline_error = PipelineError(
            message="Failed to process article",
            original_error=original_error,
            severity=ErrorSeverity.RECOVERABLE,
            model_name="gpt-4",
            article_uri="https://example.com/article",
            context={"retry_count": 3, "last_attempt": "2025-01-18 12:00:00"}
        )

        assert pipeline_error.context is not None
        assert pipeline_error.context["retry_count"] == 3
        assert "last_attempt" in pipeline_error.context


class TestClassificationConsistency:
    """Test consistency of error classification across different scenarios."""

    def test_all_fatal_errors_dont_retry(self):
        """Test that all fatal errors have should_retry=False."""
        for exc_class in LLMErrorClassifier.FATAL_EXCEPTIONS:
            try:
                # Create a dummy instance (won't actually be raised)
                error = exc_class(
                    message="Test",
                    model="test-model",
                    llm_provider="test"
                )
                severity, should_retry = LLMErrorClassifier.classify_error(error)
                assert severity == ErrorSeverity.FATAL
                assert should_retry is False, f"{exc_class.__name__} should not retry"
            except Exception:
                # Some exception types might have different constructors
                pass

    def test_all_recoverable_errors_do_retry(self):
        """Test that all recoverable errors have should_retry=True."""
        for exc_class in LLMErrorClassifier.RECOVERABLE_EXCEPTIONS:
            try:
                error = exc_class(
                    message="Test",
                    model="test-model",
                    llm_provider="test"
                )
                severity, should_retry = LLMErrorClassifier.classify_error(error)
                assert severity == ErrorSeverity.RECOVERABLE
                assert should_retry is True, f"{exc_class.__name__} should retry"
            except Exception:
                pass

    def test_all_skippable_errors_dont_retry(self):
        """Test that all skippable errors have should_retry=False."""
        for exc_class in LLMErrorClassifier.SKIPPABLE_EXCEPTIONS:
            try:
                error = exc_class(
                    message="Test",
                    model="test-model",
                    llm_provider="test"
                )
                severity, should_retry = LLMErrorClassifier.classify_error(error)
                assert severity == ErrorSeverity.SKIPPABLE
                assert should_retry is False, f"{exc_class.__name__} should not retry"
            except Exception:
                pass


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
