"""
Retry utilities with exponential backoff for transient errors.

This module provides retry logic for handling transient failures from LLM APIs,
including rate limits, timeouts, and network errors.
"""
import asyncio
import logging
import time
from typing import Callable, Any, Optional, Type, Tuple
from functools import wraps
import random

logger = logging.getLogger(__name__)


class RetryError(Exception):
    """Exception raised when all retry attempts are exhausted."""

    def __init__(self, message: str, last_exception: Exception, attempt_count: int):
        """
        Initialize RetryError.

        Args:
            message: Error message
            last_exception: The last exception that caused the retry to fail
            attempt_count: Number of attempts made
        """
        super().__init__(message)
        self.message = message
        self.last_exception = last_exception
        self.attempt_count = attempt_count

    def __str__(self):
        return f"{self.message} (after {self.attempt_count} attempts). Last error: {self.last_exception}"


class RetryConfig:
    """Configuration for retry behavior"""

    def __init__(
        self,
        max_attempts: int = 3,
        base_delay: float = 1.0,
        max_delay: float = 60.0,
        exponential_base: float = 2.0,
        jitter: bool = True
    ):
        """
        Initialize retry configuration.

        Args:
            max_attempts: Maximum number of retry attempts
            base_delay: Initial delay in seconds
            max_delay: Maximum delay in seconds (cap)
            exponential_base: Base for exponential backoff calculation
            jitter: Whether to add random jitter to prevent thundering herd
        """
        self.max_attempts = max_attempts
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.exponential_base = exponential_base
        self.jitter = jitter

    def get_delay(self, attempt: int) -> float:
        """
        Calculate delay for given attempt number.

        Args:
            attempt: Current attempt number (0-indexed)

        Returns:
            float: Delay in seconds
        """
        # Exponential backoff: base_delay * (exponential_base ^ attempt)
        delay = self.base_delay * (self.exponential_base ** attempt)

        # Cap at max_delay
        delay = min(delay, self.max_delay)

        # Add jitter to prevent thundering herd problem
        if self.jitter:
            delay = delay * (0.5 + random.random())

        return delay


async def retry_with_backoff(
    func: Callable,
    *args,
    retryable_exceptions: Tuple[Type[Exception], ...] = (Exception,),
    config: Optional[RetryConfig] = None,
    on_retry: Optional[Callable] = None,
    **kwargs
) -> Any:
    """
    Retry async function with exponential backoff.

    Args:
        func: Async function to retry
        *args: Positional arguments for func
        retryable_exceptions: Tuple of exception types to retry on
        config: RetryConfig instance (uses default if None)
        **kwargs: Keyword arguments for func

    Returns:
        Result of successful function call

    Raises:
        Last exception if all retries exhausted
    """
    if config is None:
        config = RetryConfig()

    last_exception = None

    for attempt in range(config.max_attempts):
        try:
            if asyncio.iscoroutinefunction(func):
                result = await func(*args, **kwargs)
            else:
                # Run sync function in executor
                loop = asyncio.get_event_loop()
                result = await loop.run_in_executor(None, lambda: func(*args, **kwargs))

            # Success!
            if attempt > 0:
                logger.info(
                    f"✅ Retry succeeded on attempt {attempt + 1}/{config.max_attempts} "
                    f"for {func.__name__}"
                )
            return result

        except retryable_exceptions as e:
            last_exception = e
            error_type = type(e).__name__

            if attempt < config.max_attempts - 1:
                delay = config.get_delay(attempt)
                logger.warning(
                    f"🔄 RETRY: Attempt {attempt + 1}/{config.max_attempts} failed "
                    f"for {func.__name__}"
                )
                logger.warning(f"🔄 Error type: {error_type}")
                logger.warning(f"🔄 Error: {e}")
                logger.warning(f"🔄 Next retry in {delay:.2f}s (exponential backoff)")

                # Call callback if provided
                if on_retry:
                    on_retry(attempt + 1, e, delay)

                await asyncio.sleep(delay)
            else:
                logger.error(
                    f"❌ All {config.max_attempts} retry attempts failed for {func.__name__}"
                )
                logger.error(f"❌ Last error type: {error_type}")
                logger.error(f"❌ Last error: {e}")

        except Exception as e:
            # Non-retryable exception - raise immediately
            error_type = type(e).__name__
            logger.error(
                f"❌ Non-retryable exception on attempt {attempt + 1} for {func.__name__}: "
                f"{error_type} - {e}"
            )
            raise

    # All retries exhausted - wrap in RetryError
    raise RetryError(
        message=f"Max retry attempts ({config.max_attempts}) exceeded",
        last_exception=last_exception,
        attempt_count=config.max_attempts
    )


def retry_sync_with_backoff(
    func: Callable,
    *args,
    retryable_exceptions: Tuple[Type[Exception], ...] = (Exception,),
    config: Optional[RetryConfig] = None,
    on_retry: Optional[Callable] = None,
    **kwargs
) -> Any:
    """
    Retry synchronous function with exponential backoff.

    This is a synchronous version of retry_with_backoff that doesn't
    create async event loops, preventing RuntimeError when called from
    async contexts.

    Args:
        func: Synchronous function to retry
        *args: Positional arguments for func
        retryable_exceptions: Tuple of exception types to retry on
        config: RetryConfig instance (uses default if None)
        **kwargs: Keyword arguments for func

    Returns:
        Result of successful function call

    Raises:
        Last exception if all retries exhausted
    """
    if config is None:
        config = RetryConfig()

    last_exception = None

    for attempt in range(config.max_attempts):
        try:
            result = func(*args, **kwargs)

            # Success!
            if attempt > 0:
                logger.info(
                    f"✅ Retry succeeded on attempt {attempt + 1}/{config.max_attempts} "
                    f"for {func.__name__}"
                )
            return result

        except retryable_exceptions as e:
            last_exception = e
            error_type = type(e).__name__

            if attempt < config.max_attempts - 1:
                delay = config.get_delay(attempt)
                logger.warning(
                    f"🔄 RETRY: Attempt {attempt + 1}/{config.max_attempts} failed "
                    f"for {func.__name__}"
                )
                logger.warning(f"🔄 Error type: {error_type}")
                logger.warning(f"🔄 Error: {e}")
                logger.warning(f"🔄 Next retry in {delay:.2f}s (exponential backoff)")

                # Call callback if provided
                if on_retry:
                    on_retry(attempt + 1, e, delay)

                time.sleep(delay)  # Use time.sleep instead of asyncio.sleep
            else:
                logger.error(
                    f"❌ All {config.max_attempts} retry attempts failed for {func.__name__}"
                )
                logger.error(f"❌ Last error type: {error_type}")
                logger.error(f"❌ Last error: {e}")

        except Exception as e:
            # Non-retryable exception - raise immediately
            error_type = type(e).__name__
            logger.error(
                f"❌ Non-retryable exception on attempt {attempt + 1} for {func.__name__}: "
                f"{error_type} - {e}"
            )
            raise

    # All retries exhausted - wrap in RetryError
    raise RetryError(
        message=f"Max retry attempts ({config.max_attempts}) exceeded",
        last_exception=last_exception,
        attempt_count=config.max_attempts
    )


def retry_on_rate_limit(max_attempts: int = 3):
    """
    Decorator for retrying on rate limit errors.

    Usage:
        @retry_on_rate_limit(max_attempts=3)
        async def my_llm_call():
            ...

    Args:
        max_attempts: Maximum number of retry attempts
    """
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            import litellm

            config = RetryConfig(
                max_attempts=max_attempts,
                base_delay=2.0,      # Start with 2 second delay
                max_delay=60.0,      # Cap at 60 seconds
                exponential_base=2.0,
                jitter=True
            )

            return await retry_with_backoff(
                func,
                *args,
                retryable_exceptions=(litellm.RateLimitError,),
                config=config,
                **kwargs
            )

        return wrapper
    return decorator
