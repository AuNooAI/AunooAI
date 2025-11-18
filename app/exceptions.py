"""
Exception severity classification for LiteLLM error handling strategy.

This module provides a systematic approach to classifying LiteLLM exceptions
by severity level, enabling intelligent error handling throughout the application.
"""
from enum import Enum
from typing import Type, List
import litellm


class ErrorSeverity(Enum):
    """Error severity levels determining handling strategy"""

    FATAL = "fatal"           # Stop entire pipeline immediately
    RECOVERABLE = "recoverable"  # Retry with exponential backoff
    SKIPPABLE = "skippable"   # Skip current item, continue processing
    DEGRADED = "degraded"     # Continue with fallback/reduced functionality


class LLMErrorClassifier:
    """Classifies LiteLLM exceptions by severity level"""

    # Fatal errors - must stop processing immediately
    FATAL_EXCEPTIONS: List[Type[Exception]] = [
        litellm.AuthenticationError,  # Invalid API key - can't recover
        litellm.BudgetExceededError,  # Budget/quota exceeded - can't continue
    ]

    # Recoverable errors - retry with exponential backoff
    RECOVERABLE_EXCEPTIONS: List[Type[Exception]] = [
        litellm.RateLimitError,        # Wait and retry
        litellm.Timeout,                # Network timeout - retry
        litellm.APIConnectionError,     # Network issue - retry
    ]

    # Skippable errors - skip this item, continue with next
    SKIPPABLE_EXCEPTIONS: List[Type[Exception]] = [
        litellm.ContextWindowExceededError,  # Content too large
        litellm.BadRequestError,              # Invalid input
        litellm.InvalidRequestError,          # Invalid request structure
        litellm.JSONSchemaValidationError,    # Response validation failed
    ]

    # Degraded errors - try fallback model/reduced functionality
    DEGRADED_EXCEPTIONS: List[Type[Exception]] = [
        litellm.ServiceUnavailableError,  # Provider down - try fallback
        litellm.APIError,                  # Generic API error - try fallback
    ]

    @classmethod
    def classify(cls, exception: Exception) -> ErrorSeverity:
        """
        Classify an exception by severity level.

        Args:
            exception: The exception to classify

        Returns:
            ErrorSeverity: The severity level of the exception
        """
        if isinstance(exception, tuple(cls.FATAL_EXCEPTIONS)):
            return ErrorSeverity.FATAL
        elif isinstance(exception, tuple(cls.RECOVERABLE_EXCEPTIONS)):
            return ErrorSeverity.RECOVERABLE
        elif isinstance(exception, tuple(cls.SKIPPABLE_EXCEPTIONS)):
            return ErrorSeverity.SKIPPABLE
        elif isinstance(exception, tuple(cls.DEGRADED_EXCEPTIONS)):
            return ErrorSeverity.DEGRADED
        else:
            # Unknown errors are treated as fatal (fail-safe)
            return ErrorSeverity.FATAL

    @classmethod
    def should_bail_out(cls, exception: Exception) -> bool:
        """
        Determine if exception requires immediate pipeline stop.

        Args:
            exception: The exception to check

        Returns:
            bool: True if pipeline should stop immediately
        """
        return cls.classify(exception) == ErrorSeverity.FATAL


class PipelineError(Exception):
    """
    Base exception for pipeline errors with severity tracking.

    This exception wraps LiteLLM errors and adds severity classification
    for proper error handling throughout the pipeline.
    """

    def __init__(self, message: str, severity: ErrorSeverity,
                 original_exception: Exception = None):
        """
        Initialize pipeline error.

        Args:
            message: Human-readable error message
            severity: ErrorSeverity level
            original_exception: The original LiteLLM exception (if any)
        """
        super().__init__(message)
        self.severity = severity
        self.original_exception = original_exception

    def __str__(self):
        """String representation including severity"""
        base_msg = super().__str__()
        if self.original_exception:
            return f"[{self.severity.value}] {base_msg} (caused by: {self.original_exception})"
        return f"[{self.severity.value}] {base_msg}"
