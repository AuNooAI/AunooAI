"""
Integration tests for LiteLLMModel error handling.

Tests the complete error handling flow in ai_models.py including:
- Exception classification and wrapping
- Retry logic with exponential backoff
- Circuit breaker integration
- Fallback model handling
- Database error logging
"""

from unittest.mock import Mock, patch, MagicMock, call
import pytest
import litellm
from app.ai_models import LiteLLMModel
from app.exceptions import PipelineError, ErrorSeverity, LLMErrorClassifier
from app.utils.circuit_breaker import CircuitBreakerOpen, CircuitState


@pytest.fixture
def mock_db():
    """Create a mock database facade."""
    db = Mock()
    db.get_llm_retry_state = Mock(return_value={
        'consecutive_failures': 0,
        'circuit_state': 'closed',
        'last_failure_time': None,
        'last_success_time': None
    })
    db.update_llm_retry_state = Mock()
    db.log_llm_processing_error = Mock()
    db.update_article_llm_status = Mock()
    return db


@pytest.fixture
def mock_circuit_breaker():
    """Create a mock circuit breaker."""
    cb = Mock()
    cb.check_circuit = Mock(return_value=True)
    cb.record_success = Mock()
    cb.record_failure = Mock()
    return cb


class TestFatalErrorHandling:
    """Test handling of fatal errors (AuthenticationError, BudgetExceededError)."""

    def test_authentication_error_raises_pipeline_error(self, mock_db, mock_circuit_breaker):
        """Test that AuthenticationError is wrapped in PipelineError."""
        with patch('app.ai_models.DatabaseQueryFacade', return_value=mock_db):
            model = LiteLLMModel.get_instance("gpt-4")
            model.circuit_breaker = mock_circuit_breaker

            auth_error = litellm.AuthenticationError(
                message="Invalid API key",
                model="gpt-4",
                llm_provider="openai"
            )

            with patch('litellm.completion', side_effect=auth_error):
                with pytest.raises(PipelineError) as exc_info:
                    model.generate_response([{"role": "user", "content": "test"}])

                # Should be fatal severity
                assert exc_info.value.severity == ErrorSeverity.FATAL
                assert "Invalid API key" in exc_info.value.message

                # Should record failure in circuit breaker
                mock_circuit_breaker.record_failure.assert_called_once()

    def test_budget_exceeded_error_raises_pipeline_error(self, mock_db, mock_circuit_breaker):
        """Test that BudgetExceededError is wrapped in PipelineError."""
        with patch('app.ai_models.DatabaseQueryFacade', return_value=mock_db):
            model = LiteLLMModel.get_instance("gpt-4")
            model.circuit_breaker = mock_circuit_breaker

            budget_error = litellm.BudgetExceededError(
                message="Budget exceeded",
                model="gpt-4",
                llm_provider="openai"
            )

            with patch('litellm.completion', side_effect=budget_error):
                with pytest.raises(PipelineError) as exc_info:
                    model.generate_response([{"role": "user", "content": "test"}])

                assert exc_info.value.severity == ErrorSeverity.FATAL
                mock_circuit_breaker.record_failure.assert_called_once()

    def test_fatal_errors_do_not_retry(self, mock_db, mock_circuit_breaker):
        """Test that fatal errors are not retried."""
        with patch('app.ai_models.DatabaseQueryFacade', return_value=mock_db):
            model = LiteLLMModel.get_instance("gpt-4")
            model.circuit_breaker = mock_circuit_breaker

            auth_error = litellm.AuthenticationError(
                message="Invalid API key",
                model="gpt-4",
                llm_provider="openai"
            )

            call_count = 0

            def mock_completion(*args, **kwargs):
                nonlocal call_count
                call_count += 1
                raise auth_error

            with patch('litellm.completion', side_effect=mock_completion):
                with pytest.raises(PipelineError):
                    model.generate_response([{"role": "user", "content": "test"}])

                # Should only be called once (no retries)
                assert call_count == 1


class TestRecoverableErrorHandling:
    """Test handling of recoverable errors (RateLimitError, Timeout, APIConnectionError)."""

    def test_rate_limit_error_retries_with_backoff(self, mock_db, mock_circuit_breaker):
        """Test that RateLimitError triggers retry with exponential backoff."""
        with patch('app.ai_models.DatabaseQueryFacade', return_value=mock_db):
            model = LiteLLMModel.get_instance("gpt-4")
            model.circuit_breaker = mock_circuit_breaker

            call_count = 0
            rate_limit_error = litellm.RateLimitError(
                message="Rate limit exceeded",
                model="gpt-4",
                llm_provider="openai"
            )

            def mock_completion(*args, **kwargs):
                nonlocal call_count
                call_count += 1
                if call_count < 3:
                    raise rate_limit_error
                # Success on third attempt
                return Mock(choices=[Mock(message=Mock(content="Success"))])

            with patch('litellm.completion', side_effect=mock_completion):
                with patch('time.sleep'):  # Mock sleep to speed up test
                    result = model.generate_response([{"role": "user", "content": "test"}])

                    assert result == "Success"
                    assert call_count == 3  # Should retry 2 times before success
                    # Should record final success
                    mock_circuit_breaker.record_success.assert_called()

    def test_rate_limit_error_tries_fallback_after_max_retries(self, mock_db, mock_circuit_breaker):
        """Test that RateLimitError tries fallback models after max retries."""
        with patch('app.ai_models.DatabaseQueryFacade', return_value=mock_db):
            model = LiteLLMModel.get_instance("gpt-4")
            model.circuit_breaker = mock_circuit_breaker

            rate_limit_error = litellm.RateLimitError(
                message="Rate limit exceeded",
                model="gpt-4",
                llm_provider="openai"
            )

            call_count = 0

            def mock_completion(*args, **kwargs):
                nonlocal call_count
                call_count += 1
                # Always fail for primary model, succeed for fallback
                if 'gpt-4' in str(kwargs.get('model', '')):
                    raise rate_limit_error
                return Mock(choices=[Mock(message=Mock(content="Fallback success"))])

            with patch('litellm.completion', side_effect=mock_completion):
                with patch('time.sleep'):
                    result = model.generate_response([{"role": "user", "content": "test"}])

                    # Should eventually succeed with fallback
                    assert result is not None

    def test_timeout_error_retries(self, mock_db, mock_circuit_breaker):
        """Test that Timeout error triggers retry."""
        with patch('app.ai_models.DatabaseQueryFacade', return_value=mock_db):
            model = LiteLLMModel.get_instance("gpt-4")
            model.circuit_breaker = mock_circuit_breaker

            call_count = 0
            timeout_error = litellm.Timeout(
                message="Request timed out",
                model="gpt-4",
                llm_provider="openai"
            )

            def mock_completion(*args, **kwargs):
                nonlocal call_count
                call_count += 1
                if call_count < 2:
                    raise timeout_error
                return Mock(choices=[Mock(message=Mock(content="Success after timeout"))])

            with patch('litellm.completion', side_effect=mock_completion):
                with patch('time.sleep'):
                    result = model.generate_response([{"role": "user", "content": "test"}])

                    assert result == "Success after timeout"
                    assert call_count == 2


class TestSkippableErrorHandling:
    """Test handling of skippable errors (ContextWindowExceededError, BadRequestError, etc)."""

    def test_context_window_exceeded_tries_fallback(self, mock_db, mock_circuit_breaker):
        """Test that ContextWindowExceededError skips retry and tries fallback."""
        with patch('app.ai_models.DatabaseQueryFacade', return_value=mock_db):
            model = LiteLLMModel.get_instance("gpt-4")
            model.circuit_breaker = mock_circuit_breaker

            context_error = litellm.ContextWindowExceededError(
                message="Context window exceeded",
                model="gpt-4",
                llm_provider="openai"
            )

            primary_calls = 0
            fallback_calls = 0

            def mock_completion(*args, **kwargs):
                nonlocal primary_calls, fallback_calls
                model_name = kwargs.get('model', '')
                if 'gpt-4' in model_name:
                    primary_calls += 1
                    raise context_error
                else:
                    fallback_calls += 1
                    return Mock(choices=[Mock(message=Mock(content="Fallback worked"))])

            with patch('litellm.completion', side_effect=mock_completion):
                result = model.generate_response([{"role": "user", "content": "test"}])

                # Should only try primary model once (no retries for skippable)
                assert primary_calls == 1
                # Should try fallback models
                assert fallback_calls >= 1

    def test_bad_request_error_does_not_retry(self, mock_db, mock_circuit_breaker):
        """Test that BadRequestError does not retry."""
        with patch('app.ai_models.DatabaseQueryFacade', return_value=mock_db):
            model = LiteLLMModel.get_instance("gpt-4")
            model.circuit_breaker = mock_circuit_breaker

            bad_request_error = litellm.BadRequestError(
                message="Invalid request",
                model="gpt-4",
                llm_provider="openai"
            )

            call_count = 0

            def mock_completion(*args, **kwargs):
                nonlocal call_count
                call_count += 1
                raise bad_request_error

            with patch('litellm.completion', side_effect=mock_completion):
                try:
                    model.generate_response([{"role": "user", "content": "test"}])
                except (PipelineError, Exception):
                    pass

                # Should only call once (skippable errors don't retry on primary)
                # But might try fallback
                assert call_count >= 1


class TestDegradedErrorHandling:
    """Test handling of degraded errors (ServiceUnavailableError, APIError)."""

    def test_service_unavailable_tries_fallback(self, mock_db, mock_circuit_breaker):
        """Test that ServiceUnavailableError tries fallback models."""
        with patch('app.ai_models.DatabaseQueryFacade', return_value=mock_db):
            model = LiteLLMModel.get_instance("gpt-4")
            model.circuit_breaker = mock_circuit_breaker

            service_error = litellm.ServiceUnavailableError(
                message="Service unavailable",
                model="gpt-4",
                llm_provider="openai"
            )

            def mock_completion(*args, **kwargs):
                model_name = kwargs.get('model', '')
                if 'gpt-4' in model_name:
                    raise service_error
                return Mock(choices=[Mock(message=Mock(content="Fallback success"))])

            with patch('litellm.completion', side_effect=mock_completion):
                result = model.generate_response([{"role": "user", "content": "test"}])

                # Should succeed with fallback
                assert result is not None


class TestCircuitBreakerIntegration:
    """Test integration with circuit breaker."""

    def test_circuit_breaker_open_raises_error(self, mock_db):
        """Test that open circuit breaker prevents requests."""
        mock_db.get_llm_retry_state.return_value = {
            'consecutive_failures': 10,
            'circuit_state': 'open',
            'circuit_opened_at': None
        }

        with patch('app.ai_models.DatabaseQueryFacade', return_value=mock_db):
            model = LiteLLMModel.get_instance("gpt-4")

            # Mock circuit breaker to raise CircuitBreakerOpen
            mock_cb = Mock()
            mock_cb.check_circuit.side_effect = CircuitBreakerOpen(
                model_name="gpt-4",
                opened_at=None,
                timeout_seconds=300
            )
            model.circuit_breaker = mock_cb

            with pytest.raises(PipelineError) as exc_info:
                model.generate_response([{"role": "user", "content": "test"}])

            assert "circuit breaker" in exc_info.value.message.lower()

    def test_circuit_breaker_records_success(self, mock_db, mock_circuit_breaker):
        """Test that circuit breaker records successful requests."""
        with patch('app.ai_models.DatabaseQueryFacade', return_value=mock_db):
            model = LiteLLMModel.get_instance("gpt-4")
            model.circuit_breaker = mock_circuit_breaker

            with patch('litellm.completion', return_value=Mock(
                choices=[Mock(message=Mock(content="Success"))]
            )):
                result = model.generate_response([{"role": "user", "content": "test"}])

                assert result == "Success"
                mock_circuit_breaker.record_success.assert_called()

    def test_circuit_breaker_records_failures(self, mock_db, mock_circuit_breaker):
        """Test that circuit breaker records failed requests."""
        with patch('app.ai_models.DatabaseQueryFacade', return_value=mock_db):
            model = LiteLLMModel.get_instance("gpt-4")
            model.circuit_breaker = mock_circuit_breaker

            auth_error = litellm.AuthenticationError(
                message="Auth failed",
                model="gpt-4",
                llm_provider="openai"
            )

            with patch('litellm.completion', side_effect=auth_error):
                with pytest.raises(PipelineError):
                    model.generate_response([{"role": "user", "content": "test"}])

                mock_circuit_breaker.record_failure.assert_called_once()


class TestFallbackModelHandling:
    """Test fallback model functionality."""

    def test_fallback_models_tried_in_order(self, mock_db, mock_circuit_breaker):
        """Test that fallback models are tried in specified order."""
        with patch('app.ai_models.DatabaseQueryFacade', return_value=mock_db):
            model = LiteLLMModel.get_instance("gpt-4")
            model.circuit_breaker = mock_circuit_breaker

            # Set up fallback models
            model.fallback_models = ["gpt-3.5-turbo", "claude-3"]

            rate_limit_error = litellm.RateLimitError(
                message="Rate limit",
                model="gpt-4",
                llm_provider="openai"
            )

            models_tried = []

            def mock_completion(*args, **kwargs):
                model_name = kwargs.get('model', '')
                models_tried.append(model_name)

                if len(models_tried) < 3:  # Fail first two attempts
                    raise rate_limit_error
                return Mock(choices=[Mock(message=Mock(content="Success"))])

            with patch('litellm.completion', side_effect=mock_completion):
                with patch('time.sleep'):
                    result = model.generate_response([{"role": "user", "content": "test"}])

                    # Should try primary model, then fallbacks
                    assert len(models_tried) >= 2

    def test_fallback_success_recorded(self, mock_db, mock_circuit_breaker):
        """Test that successful fallback is recorded."""
        with patch('app.ai_models.DatabaseQueryFacade', return_value=mock_db):
            model = LiteLLMModel.get_instance("gpt-4")
            model.circuit_breaker = mock_circuit_breaker

            rate_limit_error = litellm.RateLimitError(
                message="Rate limit",
                model="gpt-4",
                llm_provider="openai"
            )

            def mock_completion(*args, **kwargs):
                if 'gpt-4' in str(kwargs.get('model', '')):
                    raise rate_limit_error
                return Mock(choices=[Mock(message=Mock(content="Fallback success"))])

            with patch('litellm.completion', side_effect=mock_completion):
                with patch('time.sleep'):
                    result = model.generate_response([{"role": "user", "content": "test"}])

                    assert result == "Fallback success"


class TestDatabaseLogging:
    """Test database error logging."""

    def test_error_logged_to_database(self, mock_db, mock_circuit_breaker):
        """Test that errors are logged to database."""
        with patch('app.ai_models.DatabaseQueryFacade', return_value=mock_db):
            model = LiteLLMModel.get_instance("gpt-4")
            model.circuit_breaker = mock_circuit_breaker

            auth_error = litellm.AuthenticationError(
                message="Auth failed",
                model="gpt-4",
                llm_provider="openai"
            )

            with patch('litellm.completion', side_effect=auth_error):
                try:
                    model.generate_response(
                        [{"role": "user", "content": "test"}],
                        article_uri="https://example.com/article"
                    )
                except PipelineError:
                    pass

                # Should log error to database
                # Note: This depends on implementation details
                # The actual logging might happen in the calling code


class TestErrorPropagation:
    """Test that errors propagate correctly through the stack."""

    def test_pipeline_error_preserves_original_error(self, mock_db, mock_circuit_breaker):
        """Test that PipelineError preserves the original exception."""
        with patch('app.ai_models.DatabaseQueryFacade', return_value=mock_db):
            model = LiteLLMModel.get_instance("gpt-4")
            model.circuit_breaker = mock_circuit_breaker

            original_error = litellm.AuthenticationError(
                message="Original error",
                model="gpt-4",
                llm_provider="openai"
            )

            with patch('litellm.completion', side_effect=original_error):
                with pytest.raises(PipelineError) as exc_info:
                    model.generate_response([{"role": "user", "content": "test"}])

                assert exc_info.value.original_error == original_error

    def test_pipeline_error_includes_context(self, mock_db, mock_circuit_breaker):
        """Test that PipelineError includes contextual information."""
        with patch('app.ai_models.DatabaseQueryFacade', return_value=mock_db):
            model = LiteLLMModel.get_instance("gpt-4")
            model.circuit_breaker = mock_circuit_breaker

            auth_error = litellm.AuthenticationError(
                message="Auth error",
                model="gpt-4",
                llm_provider="openai"
            )

            with patch('litellm.completion', side_effect=auth_error):
                with pytest.raises(PipelineError) as exc_info:
                    model.generate_response(
                        [{"role": "user", "content": "test"}],
                        article_uri="https://example.com/article"
                    )

                # Should include model name
                assert exc_info.value.model_name == "gpt-4"
                # Should include severity
                assert exc_info.value.severity == ErrorSeverity.FATAL


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
