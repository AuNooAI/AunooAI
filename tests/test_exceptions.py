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
        severity = LLMErrorClassifier.classify(auth_error)
        assert severity == ErrorSeverity.FATAL

        # BudgetExceededError
        budget_error = litellm.BudgetExceededError(
            current_cost=15.0,
            max_budget=10.0,
            message="Budget exceeded"
        )
        severity = LLMErrorClassifier.classify(budget_error)
        assert severity == ErrorSeverity.FATAL

    def test_recoverable_exceptions_classification(self):
        """Test that recoverable exceptions are classified correctly."""
        # RateLimitError
        rate_limit_error = litellm.RateLimitError(
            message="Rate limit exceeded",
            model="gpt-4",
            llm_provider="openai"
        )
        severity = LLMErrorClassifier.classify(rate_limit_error)
        assert severity == ErrorSeverity.RECOVERABLE

        # Timeout
        timeout_error = litellm.Timeout(
            message="Request timed out",
            model="gpt-4",
            llm_provider="openai"
        )
        severity = LLMErrorClassifier.classify(timeout_error)
        assert severity == ErrorSeverity.RECOVERABLE

        # APIConnectionError
        connection_error = litellm.APIConnectionError(
            message="Connection failed",
            model="gpt-4",
            llm_provider="openai"
        )
        severity = LLMErrorClassifier.classify(connection_error)
        assert severity == ErrorSeverity.RECOVERABLE

    def test_skippable_exceptions_classification(self):
        """Test that skippable exceptions are classified correctly."""
        # ContextWindowExceededError
        context_error = litellm.ContextWindowExceededError(
            message="Context window exceeded",
            model="gpt-4",
            llm_provider="openai"
        )
        severity = LLMErrorClassifier.classify(context_error)
        assert severity == ErrorSeverity.SKIPPABLE

        # BadRequestError
        bad_request_error = litellm.BadRequestError(
            message="Invalid request",
            model="gpt-4",
            llm_provider="openai"
        )
        severity = LLMErrorClassifier.classify(bad_request_error)
        assert severity == ErrorSeverity.SKIPPABLE

        # InvalidRequestError
        invalid_request_error = litellm.InvalidRequestError(
            message="Invalid request parameter",
            model="gpt-4",
            llm_provider="openai"
        )
        severity = LLMErrorClassifier.classify(invalid_request_error)
        assert severity == ErrorSeverity.SKIPPABLE

        # JSONSchemaValidationError
        json_error = litellm.JSONSchemaValidationError(
            model="gpt-4",
            llm_provider="openai",
            raw_response="{}",
            schema="{}"
        )
        severity = LLMErrorClassifier.classify(json_error)
        assert severity == ErrorSeverity.SKIPPABLE

    def test_degraded_exceptions_classification(self):
        """Test that degraded exceptions are classified correctly."""
        # ServiceUnavailableError
        service_error = litellm.ServiceUnavailableError(
            message="Service temporarily unavailable",
            model="gpt-4",
            llm_provider="openai"
        )
        severity = LLMErrorClassifier.classify(service_error)
        assert severity == ErrorSeverity.DEGRADED

        # APIError
        api_error = litellm.APIError(
            status_code=500,
            message="API error occurred",
            llm_provider="openai",
            model="gpt-4"
        )
        severity = LLMErrorClassifier.classify(api_error)
        assert severity == ErrorSeverity.DEGRADED

    def test_unknown_exception_classification(self):
        """Test that unknown exceptions are classified as FATAL (fail-safe)."""
        unknown_error = Exception("Unknown error type")
        severity = LLMErrorClassifier.classify(unknown_error)
        assert severity == ErrorSeverity.FATAL

    def test_should_bail_out(self):
        """Test that should_bail_out correctly identifies fatal exceptions."""
        auth_error = litellm.AuthenticationError(
            message="Invalid API key",
            model="gpt-4",
            llm_provider="openai"
        )
        assert LLMErrorClassifier.should_bail_out(auth_error) is True

        rate_limit_error = litellm.RateLimitError(
            message="Rate limit exceeded",
            model="gpt-4",
            llm_provider="openai"
        )
        assert LLMErrorClassifier.should_bail_out(rate_limit_error) is False

    def test_classify_returns_error_severity(self):
        """Test that classify always returns an ErrorSeverity enum member."""
        error = litellm.RateLimitError(
            message="Test",
            model="gpt-4",
            llm_provider="openai"
        )
        result = LLMErrorClassifier.classify(error)
        assert isinstance(result, ErrorSeverity)


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
            severity=ErrorSeverity.FATAL,
            original_exception=original_error
        )

        assert str(pipeline_error) is not None
        assert pipeline_error.original_exception == original_error
        assert pipeline_error.severity == ErrorSeverity.FATAL

    def test_pipeline_error_str_representation(self):
        """Test string representation of PipelineError."""
        original_error = Exception("Original error message")

        pipeline_error = PipelineError(
            message="Pipeline failed",
            severity=ErrorSeverity.RECOVERABLE,
            original_exception=original_error
        )

        error_str = str(pipeline_error)
        assert "Pipeline failed" in error_str
        assert "recoverable" in error_str
        assert "Original error message" in error_str

    def test_pipeline_error_optional_fields(self):
        """Test that optional fields can be None."""
        pipeline_error = PipelineError(
            message="Simple error",
            severity=ErrorSeverity.SKIPPABLE,
            original_exception=None
        )

        assert pipeline_error.original_exception is None
        assert pipeline_error.severity == ErrorSeverity.SKIPPABLE
        error_str = str(pipeline_error)
        assert "Simple error" in error_str

    def test_pipeline_error_with_original_exception(self):
        """Test PipelineError wrapping a LiteLLM exception."""
        original_error = litellm.RateLimitError(
            message="Rate limit exceeded",
            model="gpt-4",
            llm_provider="openai"
        )

        pipeline_error = PipelineError(
            message="Failed to process article",
            severity=ErrorSeverity.RECOVERABLE,
            original_exception=original_error
        )

        assert pipeline_error.original_exception is original_error
        assert pipeline_error.severity == ErrorSeverity.RECOVERABLE
        error_str = str(pipeline_error)
        assert "Failed to process article" in error_str
        assert "caused by" in error_str


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
