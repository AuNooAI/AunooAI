"""
Unit tests for retry utilities with exponential backoff.

Tests the retry logic for both synchronous and asynchronous functions,
including exponential backoff, jitter, and retry configuration.
"""

from unittest.mock import Mock, patch, call
import pytest
import asyncio
import time
from app.utils.retry import (
    RetryConfig,
    retry_with_backoff,
    retry_sync_with_backoff,
    RetryError
)


class TestRetryConfig:
    """Test the RetryConfig dataclass."""

    def test_default_config(self):
        """Test default retry configuration values."""
        config = RetryConfig()
        assert config.max_attempts == 3
        assert config.base_delay == 1.0
        assert config.max_delay == 60.0
        assert config.exponential_base == 2.0
        assert config.jitter is True

    def test_custom_config(self):
        """Test custom retry configuration."""
        config = RetryConfig(
            max_attempts=5,
            base_delay=2.0,
            max_delay=120.0,
            exponential_base=3.0,
            jitter=False
        )
        assert config.max_attempts == 5
        assert config.base_delay == 2.0
        assert config.max_delay == 120.0
        assert config.exponential_base == 3.0
        assert config.jitter is False

    def test_config_validation(self):
        """Test that invalid config values are handled."""
        # Should not raise errors for reasonable values
        config = RetryConfig(max_attempts=1, base_delay=0.1, max_delay=1.0)
        assert config.max_attempts == 1


class TestRetrySyncWithBackoff:
    """Test synchronous retry with exponential backoff."""

    def test_success_on_first_attempt(self):
        """Test that successful function doesn't retry."""
        mock_func = Mock(return_value="success")

        result = retry_sync_with_backoff(mock_func, arg1="test", kwarg1="value")

        assert result == "success"
        assert mock_func.call_count == 1
        mock_func.assert_called_once_with(arg1="test", kwarg1="value")

    def test_success_after_retries(self):
        """Test that function succeeds after some failures."""
        mock_func = Mock(side_effect=[
            ValueError("Fail 1"),
            ValueError("Fail 2"),
            "success"
        ])

        config = RetryConfig(max_attempts=3, base_delay=0.01, jitter=False)
        result = retry_sync_with_backoff(
            mock_func,
            retryable_exceptions=(ValueError,),
            config=config
        )

        assert result == "success"
        assert mock_func.call_count == 3

    def test_max_attempts_exceeded(self):
        """Test that RetryError is raised after max attempts."""
        mock_func = Mock(side_effect=ValueError("Always fails"))

        config = RetryConfig(max_attempts=3, base_delay=0.01)

        with pytest.raises(RetryError) as exc_info:
            retry_sync_with_backoff(
                mock_func,
                retryable_exceptions=(ValueError,),
                config=config
            )

        assert mock_func.call_count == 3
        assert "Max retry attempts (3) exceeded" in str(exc_info.value)
        assert isinstance(exc_info.value.last_exception, ValueError)

    def test_non_retryable_exception(self):
        """Test that non-retryable exceptions are raised immediately."""
        mock_func = Mock(side_effect=RuntimeError("Fatal error"))

        config = RetryConfig(max_attempts=3, base_delay=0.01)

        with pytest.raises(RuntimeError, match="Fatal error"):
            retry_sync_with_backoff(
                mock_func,
                retryable_exceptions=(ValueError,),
                config=config
            )

        # Should fail immediately without retries
        assert mock_func.call_count == 1

    def test_exponential_backoff_delays(self):
        """Test that delays increase exponentially."""
        mock_func = Mock(side_effect=[ValueError(), ValueError(), "success"])

        config = RetryConfig(
            max_attempts=3,
            base_delay=1.0,
            exponential_base=2.0,
            jitter=False
        )

        with patch('time.sleep') as mock_sleep:
            result = retry_sync_with_backoff(
                mock_func,
                retryable_exceptions=(ValueError,),
                config=config
            )

            assert result == "success"
            # First retry: 1.0 * 2^0 = 1.0
            # Second retry: 1.0 * 2^1 = 2.0
            calls = mock_sleep.call_args_list
            assert len(calls) == 2
            assert calls[0] == call(1.0)
            assert calls[1] == call(2.0)

    def test_max_delay_cap(self):
        """Test that delay is capped at max_delay."""
        mock_func = Mock(side_effect=[ValueError(), ValueError(), "success"])

        config = RetryConfig(
            max_attempts=3,
            base_delay=50.0,
            max_delay=10.0,  # Cap at 10 seconds
            exponential_base=2.0,
            jitter=False
        )

        with patch('time.sleep') as mock_sleep:
            result = retry_sync_with_backoff(
                mock_func,
                retryable_exceptions=(ValueError,),
                config=config
            )

            # All delays should be capped at 10.0
            calls = mock_sleep.call_args_list
            for call_args in calls:
                assert call_args[0][0] <= 10.0

    def test_jitter_adds_randomness(self):
        """Test that jitter adds randomness to delays."""
        mock_func = Mock(side_effect=[ValueError(), ValueError(), "success"])

        config = RetryConfig(
            max_attempts=3,
            base_delay=1.0,
            jitter=True
        )

        delays = []
        original_sleep = time.sleep

        def capture_sleep(duration):
            delays.append(duration)
            # Don't actually sleep in tests

        with patch('time.sleep', side_effect=capture_sleep):
            result = retry_sync_with_backoff(
                mock_func,
                retryable_exceptions=(ValueError,),
                config=config
            )

            # With jitter, delays should vary
            # Expected base: 1.0, 2.0
            # With jitter: should be in range [0.5, 1.5] and [1.0, 3.0]
            assert len(delays) == 2
            assert 0.5 <= delays[0] <= 1.5
            assert 1.0 <= delays[1] <= 3.0

    def test_callback_on_retry(self):
        """Test that callback is called on each retry."""
        mock_func = Mock(side_effect=[ValueError("Fail 1"), ValueError("Fail 2"), "success"])
        mock_callback = Mock()

        config = RetryConfig(max_attempts=3, base_delay=0.01)

        retry_sync_with_backoff(
            mock_func,
            retryable_exceptions=(ValueError,),
            config=config,
            on_retry=mock_callback
        )

        # Callback should be called twice (for first two failures)
        assert mock_callback.call_count == 2


class TestRetryAsyncWithBackoff:
    """Test asynchronous retry with exponential backoff."""

    @pytest.mark.asyncio
    async def test_async_success_on_first_attempt(self):
        """Test that successful async function doesn't retry."""
        async def async_func():
            return "success"

        result = await retry_with_backoff(async_func)
        assert result == "success"

    @pytest.mark.asyncio
    async def test_async_success_after_retries(self):
        """Test that async function succeeds after some failures."""
        call_count = 0

        async def async_func():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ValueError(f"Fail {call_count}")
            return "success"

        config = RetryConfig(max_attempts=3, base_delay=0.01, jitter=False)
        result = await retry_with_backoff(
            async_func,
            retryable_exceptions=(ValueError,),
            config=config
        )

        assert result == "success"
        assert call_count == 3

    @pytest.mark.asyncio
    async def test_async_max_attempts_exceeded(self):
        """Test that RetryError is raised after max attempts in async."""
        async def async_func():
            raise ValueError("Always fails")

        config = RetryConfig(max_attempts=3, base_delay=0.01)

        with pytest.raises(RetryError) as exc_info:
            await retry_with_backoff(
                async_func,
                retryable_exceptions=(ValueError,),
                config=config
            )

        assert "Max retry attempts (3) exceeded" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_async_non_retryable_exception(self):
        """Test that non-retryable exceptions are raised immediately in async."""
        async def async_func():
            raise RuntimeError("Fatal error")

        config = RetryConfig(max_attempts=3, base_delay=0.01)

        with pytest.raises(RuntimeError, match="Fatal error"):
            await retry_with_backoff(
                async_func,
                retryable_exceptions=(ValueError,),
                config=config
            )

    @pytest.mark.asyncio
    async def test_async_exponential_backoff(self):
        """Test that async delays increase exponentially."""
        call_count = 0

        async def async_func():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ValueError()
            return "success"

        config = RetryConfig(
            max_attempts=3,
            base_delay=0.1,
            exponential_base=2.0,
            jitter=False
        )

        with patch('asyncio.sleep') as mock_sleep:
            mock_sleep.return_value = asyncio.Future()
            mock_sleep.return_value.set_result(None)

            result = await retry_with_backoff(
                async_func,
                retryable_exceptions=(ValueError,),
                config=config
            )

            assert result == "success"
            # Should have 2 sleeps (between 3 attempts)
            assert mock_sleep.call_count == 2

    @pytest.mark.asyncio
    async def test_async_with_args_and_kwargs(self):
        """Test async retry with function arguments."""
        async def async_func(arg1, arg2, kwarg1=None):
            return f"{arg1}-{arg2}-{kwarg1}"

        result = await retry_with_backoff(
            async_func,
            "test1",
            "test2",
            kwarg1="test3"
        )

        assert result == "test1-test2-test3"


class TestRetryError:
    """Test the RetryError exception."""

    def test_retry_error_creation(self):
        """Test creating a RetryError."""
        original_error = ValueError("Original error")
        retry_error = RetryError(
            message="Retry failed",
            last_exception=original_error,
            attempt_count=3
        )

        assert retry_error.message == "Retry failed"
        assert retry_error.last_exception == original_error
        assert retry_error.attempt_count == 3

    def test_retry_error_string_representation(self):
        """Test string representation of RetryError."""
        original_error = ValueError("Original error")
        retry_error = RetryError(
            message="Max retries exceeded",
            last_exception=original_error,
            attempt_count=5
        )

        error_str = str(retry_error)
        assert "Max retries exceeded" in error_str
        assert "5" in error_str


class TestRetryIntegration:
    """Integration tests for retry functionality."""

    def test_retry_with_multiple_exception_types(self):
        """Test retry with multiple retryable exception types."""
        call_count = 0

        def func():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise ValueError("First failure")
            elif call_count == 2:
                raise ConnectionError("Second failure")
            return "success"

        config = RetryConfig(max_attempts=3, base_delay=0.01)
        result = retry_sync_with_backoff(
            func,
            retryable_exceptions=(ValueError, ConnectionError),
            config=config
        )

        assert result == "success"
        assert call_count == 3

    def test_retry_preserves_return_value(self):
        """Test that retry preserves complex return values."""
        def func():
            return {"status": "ok", "data": [1, 2, 3]}

        result = retry_sync_with_backoff(func)
        assert result == {"status": "ok", "data": [1, 2, 3]}

    @pytest.mark.asyncio
    async def test_async_retry_with_real_delays(self):
        """Test async retry with actual (small) delays."""
        call_count = 0
        start_time = time.time()

        async def async_func():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ValueError()
            return "success"

        config = RetryConfig(max_attempts=3, base_delay=0.01, jitter=False)
        result = await retry_with_backoff(
            async_func,
            retryable_exceptions=(ValueError,),
            config=config
        )

        elapsed = time.time() - start_time
        assert result == "success"
        assert call_count == 3
        # Should have waited approximately 0.01 + 0.02 = 0.03 seconds
        assert elapsed >= 0.03


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
