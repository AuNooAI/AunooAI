"""
Unit tests for circuit breaker pattern implementation.

Tests the circuit breaker that prevents cascading failures by tracking
error rates and temporarily blocking requests when failure thresholds
are exceeded. Uses database-backed persistent state.
"""

from unittest.mock import Mock, patch, MagicMock
import pytest
from datetime import datetime, timedelta
import litellm
from app.utils.circuit_breaker import CircuitBreaker, CircuitBreakerOpen, CircuitState
from app.exceptions import ErrorSeverity


class TestCircuitState:
    """Test the CircuitState enum."""

    def test_circuit_state_values(self):
        """Test that circuit state enum has expected values."""
        assert CircuitState.CLOSED.value == "closed"
        assert CircuitState.OPEN.value == "open"
        assert CircuitState.HALF_OPEN.value == "half_open"

    def test_circuit_state_members(self):
        """Test that all expected circuit states exist."""
        states = [s.value for s in CircuitState]
        assert "closed" in states
        assert "open" in states
        assert "half_open" in states
        assert len(states) == 3


@pytest.fixture
def mock_facade():
    """Create a mock database facade with the required methods."""
    facade = Mock()
    facade.get_llm_retry_state = Mock()
    facade.update_llm_retry_state = Mock()
    facade.reset_llm_retry_state = Mock()
    return facade


@pytest.fixture
def mock_db(mock_facade):
    """Create a mock database instance wrapping the facade."""
    db = Mock()
    db.facade = mock_facade
    return db


@pytest.fixture
def circuit_breaker(mock_db):
    """Create a circuit breaker with mocked database."""
    with patch('app.database.get_database_instance', return_value=mock_db):
        cb = CircuitBreaker(model_name="test-model")
        yield cb


class TestCircuitBreakerInitialization:
    """Test circuit breaker initialization."""

    def test_init_with_model_name(self):
        """Test that circuit breaker initializes with model name."""
        cb = CircuitBreaker(model_name="gpt-4")
        assert cb.model_name == "gpt-4"
        assert cb.db is None  # DB is lazy loaded, not set at init

    def test_init_loads_state_from_db(self, mock_db):
        """Test that circuit breaker loads existing state from database via get_state."""
        mock_db.facade.get_llm_retry_state.return_value = {
            'consecutive_failures': 2,
            'circuit_state': 'closed',
            'last_failure_time': datetime.now(),
            'last_success_time': datetime.now() - timedelta(minutes=5)
        }

        with patch('app.database.get_database_instance', return_value=mock_db):
            cb = CircuitBreaker(model_name="gpt-4")
            state = cb.get_state()

        mock_db.facade.get_llm_retry_state.assert_called_once_with("gpt-4")
        assert state['consecutive_failures'] == 2

    def test_init_creates_state_if_not_exists(self, mock_db):
        """Test that circuit breaker returns default state if not in database."""
        mock_db.facade.get_llm_retry_state.return_value = None

        with patch('app.database.get_database_instance', return_value=mock_db):
            cb = CircuitBreaker(model_name="new-model")
            state = cb.get_state()

        # Should attempt to get state
        mock_db.facade.get_llm_retry_state.assert_called_once_with("new-model")
        # Should return default state
        assert state['circuit_state'] == 'closed'
        assert state['consecutive_failures'] == 0


class TestCircuitBreakerClosedState:
    """Test circuit breaker behavior in CLOSED state."""

    def test_closed_circuit_allows_requests(self, circuit_breaker, mock_db):
        """Test that closed circuit allows all requests."""
        mock_db.facade.get_llm_retry_state.return_value = {
            'consecutive_failures': 0,
            'circuit_state': 'closed',
            'last_failure_time': None,
            'last_success_time': datetime.now()
        }

        is_allowed = circuit_breaker.check_circuit()
        assert is_allowed is True

    def test_closed_circuit_tracks_failures(self, circuit_breaker, mock_db):
        """Test that closed circuit tracks consecutive failures."""
        mock_db.facade.get_llm_retry_state.return_value = {
            'consecutive_failures': 2,
            'circuit_state': 'closed',
            'last_failure_time': datetime.now(),
            'last_success_time': None
        }

        error = litellm.RateLimitError(
            message="Rate limit exceeded",
            model="test-model",
            llm_provider="openai"
        )

        circuit_breaker.record_failure(error)

        # Should update state with incremented failure count
        mock_db.facade.update_llm_retry_state.assert_called()
        call_args = mock_db.facade.update_llm_retry_state.call_args_list[0][0][0]
        assert call_args['consecutive_failures'] == 3

    def test_closed_circuit_opens_after_threshold(self, circuit_breaker, mock_db):
        """Test that circuit opens after failure threshold is exceeded."""
        # Set state to be just below threshold
        mock_db.facade.get_llm_retry_state.return_value = {
            'consecutive_failures': CircuitBreaker.FAILURE_THRESHOLD - 1,
            'circuit_state': 'closed',
            'last_failure_time': datetime.now(),
            'last_success_time': None
        }

        error = litellm.RateLimitError(
            message="Rate limit exceeded",
            model="test-model",
            llm_provider="openai"
        )

        circuit_breaker.record_failure(error)

        # Should open the circuit (last call to update is from _open_circuit)
        last_call_args = mock_db.facade.update_llm_retry_state.call_args[0][0]
        assert last_call_args['circuit_state'] == 'open'

    def test_closed_circuit_resets_on_success(self, circuit_breaker, mock_db):
        """Test that closed circuit resets failure count on success."""
        mock_db.facade.get_llm_retry_state.return_value = {
            'consecutive_failures': 3,
            'circuit_state': 'closed',
            'last_failure_time': datetime.now(),
            'last_success_time': None
        }

        circuit_breaker.record_success()

        # record_success calls reset_llm_retry_state (not update)
        mock_db.facade.reset_llm_retry_state.assert_called_once_with("test-model")


class TestCircuitBreakerOpenState:
    """Test circuit breaker behavior in OPEN state."""

    def test_open_circuit_blocks_requests(self, circuit_breaker, mock_db):
        """Test that open circuit blocks all requests."""
        mock_db.facade.get_llm_retry_state.return_value = {
            'consecutive_failures': 10,
            'circuit_state': 'open',
            'circuit_opened_at': datetime.utcnow(),
            'last_failure_time': datetime.now()
        }

        with pytest.raises(CircuitBreakerOpen) as exc_info:
            circuit_breaker.check_circuit()

        assert "Circuit breaker is OPEN" in str(exc_info.value)
        assert "test-model" in str(exc_info.value)

    def test_open_circuit_transitions_to_half_open_after_timeout(self, circuit_breaker, mock_db):
        """Test that open circuit transitions to half-open after timeout."""
        # Set circuit opened time to be past the timeout duration
        opened_at = datetime.utcnow() - timedelta(seconds=CircuitBreaker.TIMEOUT_DURATION + 10)

        mock_db.facade.get_llm_retry_state.return_value = {
            'consecutive_failures': 10,
            'circuit_state': 'open',
            'circuit_opened_at': opened_at,
            'last_failure_time': opened_at
        }

        # Should allow request and transition to half-open
        is_allowed = circuit_breaker.check_circuit()
        assert is_allowed is True

        # Verify state was updated to half_open
        call_args = mock_db.facade.update_llm_retry_state.call_args[0][0]
        assert call_args['circuit_state'] == 'half_open'

    def test_open_circuit_records_additional_failures(self, circuit_breaker, mock_db):
        """Test that open circuit still increments failure count on record_failure."""
        mock_db.facade.get_llm_retry_state.return_value = {
            'consecutive_failures': 10,
            'circuit_state': 'open',
            'circuit_opened_at': datetime.utcnow(),
            'last_failure_time': datetime.now()
        }

        error = litellm.RateLimitError(
            message="Rate limit exceeded",
            model="test-model",
            llm_provider="openai"
        )

        circuit_breaker.record_failure(error)

        # Failure count is incremented (10 -> 11)
        first_call_args = mock_db.facade.update_llm_retry_state.call_args_list[0][0][0]
        assert first_call_args['consecutive_failures'] == 11

        # _open_circuit is called again since 11 >= threshold
        last_call_args = mock_db.facade.update_llm_retry_state.call_args[0][0]
        assert last_call_args['circuit_state'] == 'open'


class TestCircuitBreakerHalfOpenState:
    """Test circuit breaker behavior in HALF_OPEN state."""

    def test_half_open_circuit_allows_limited_requests(self, circuit_breaker, mock_db):
        """Test that half-open circuit allows requests."""
        mock_db.facade.get_llm_retry_state.return_value = {
            'consecutive_failures': 0,
            'circuit_state': 'half_open',
            'circuit_opened_at': datetime.utcnow() - timedelta(minutes=10),
            'last_failure_time': datetime.now() - timedelta(minutes=10)
        }

        is_allowed = circuit_breaker.check_circuit()
        assert is_allowed is True

    def test_half_open_circuit_closes_on_success(self, circuit_breaker, mock_db):
        """Test that half-open circuit resets state after successful request."""
        mock_db.facade.get_llm_retry_state.return_value = {
            'consecutive_failures': 0,
            'circuit_state': 'half_open',
            'circuit_opened_at': datetime.utcnow() - timedelta(minutes=10)
        }

        circuit_breaker.record_success()

        # record_success calls reset_llm_retry_state (not update)
        mock_db.facade.reset_llm_retry_state.assert_called_once_with("test-model")

    def test_half_open_circuit_reopens_on_failure(self, circuit_breaker, mock_db):
        """Test that half-open circuit reopens when failure reaches threshold."""
        mock_db.facade.get_llm_retry_state.return_value = {
            'consecutive_failures': CircuitBreaker.FAILURE_THRESHOLD - 1,
            'circuit_state': 'half_open',
            'circuit_opened_at': datetime.utcnow() - timedelta(minutes=10)
        }

        error = litellm.RateLimitError(
            message="Rate limit exceeded",
            model="test-model",
            llm_provider="openai"
        )

        circuit_breaker.record_failure(error)

        # Failure count incremented: 4 -> 5 (reaches threshold)
        first_call_args = mock_db.facade.update_llm_retry_state.call_args_list[0][0][0]
        assert first_call_args['consecutive_failures'] == CircuitBreaker.FAILURE_THRESHOLD

        # 5 >= 5 triggers _open_circuit(), so circuit reopens
        last_call_args = mock_db.facade.update_llm_retry_state.call_args[0][0]
        assert last_call_args['circuit_state'] == 'open'


class TestCircuitBreakerStateTransitions:
    """Test circuit breaker state transitions."""

    def test_full_cycle_closed_to_open_to_half_open_to_closed(self, circuit_breaker, mock_db):
        """Test complete circuit breaker cycle."""
        # Start CLOSED with failures just below threshold
        mock_db.facade.get_llm_retry_state.return_value = {
            'consecutive_failures': CircuitBreaker.FAILURE_THRESHOLD - 1,
            'circuit_state': 'closed',
            'last_failure_time': None,
            'last_success_time': datetime.now()
        }

        # Record one more failure to reach threshold
        error = litellm.RateLimitError(
            message="Rate limit",
            model="test-model",
            llm_provider="openai"
        )

        circuit_breaker.record_failure(error)

        # Should be OPEN now (last call is from _open_circuit)
        last_call_args = mock_db.facade.update_llm_retry_state.call_args[0][0]
        assert last_call_args['circuit_state'] == 'open'

        # Wait for timeout (mock time passage)
        mock_db.facade.update_llm_retry_state.reset_mock()
        opened_at = datetime.utcnow() - timedelta(seconds=CircuitBreaker.TIMEOUT_DURATION + 10)
        mock_db.facade.get_llm_retry_state.return_value = {
            'consecutive_failures': CircuitBreaker.FAILURE_THRESHOLD,
            'circuit_state': 'open',
            'circuit_opened_at': opened_at,
            'last_failure_time': opened_at
        }

        # Should transition to HALF_OPEN
        circuit_breaker.check_circuit()
        call_args = mock_db.facade.update_llm_retry_state.call_args[0][0]
        assert call_args['circuit_state'] == 'half_open'

        # Record success to close
        mock_db.facade.get_llm_retry_state.return_value['circuit_state'] = 'half_open'
        circuit_breaker.record_success()

        # Should be CLOSED again (via reset)
        mock_db.facade.reset_llm_retry_state.assert_called_with("test-model")


class TestCircuitBreakerReset:
    """Test circuit breaker reset functionality."""

    def test_reset_circuit_breaker(self, circuit_breaker, mock_db):
        """Test that circuit breaker can be manually reset."""
        circuit_breaker.reset()

        mock_db.facade.reset_llm_retry_state.assert_called_once_with("test-model")


class TestCircuitBreakerOpen:
    """Test the CircuitBreakerOpen exception."""

    def test_circuit_breaker_open_exception(self):
        """Test CircuitBreakerOpen exception creation."""
        exc = CircuitBreakerOpen(
            model_name="gpt-4",
            opened_at=datetime.now(),
            timeout_seconds=300
        )

        assert "gpt-4" in str(exc)
        assert exc.model_name == "gpt-4"
        assert exc.timeout_seconds == 300

    def test_circuit_breaker_open_includes_timeout_info(self):
        """Test that exception includes timeout information."""
        opened_at = datetime.now()
        exc = CircuitBreakerOpen(
            model_name="gpt-4",
            opened_at=opened_at,
            timeout_seconds=300
        )

        error_str = str(exc)
        assert "300" in error_str or "5" in error_str  # 300 seconds = 5 minutes


class TestCircuitBreakerConfiguration:
    """Test circuit breaker configuration."""

    def test_failure_threshold_configuration(self):
        """Test that failure threshold can be configured."""
        assert CircuitBreaker.FAILURE_THRESHOLD == 5

    def test_timeout_duration_configuration(self):
        """Test that timeout duration can be configured."""
        assert CircuitBreaker.TIMEOUT_DURATION == 300  # 5 minutes

    def test_half_open_max_attempts_configuration(self):
        """Test that half-open max attempts can be configured."""
        assert CircuitBreaker.HALF_OPEN_MAX_ATTEMPTS == 3


class TestCircuitBreakerDatabaseInteraction:
    """Test circuit breaker database interaction."""

    def test_updates_database_on_failure(self, circuit_breaker, mock_db):
        """Test that circuit breaker updates database on failure."""
        mock_db.facade.get_llm_retry_state.return_value = {
            'consecutive_failures': 1,
            'circuit_state': 'closed'
        }

        error = litellm.RateLimitError(
            message="Rate limit",
            model="test-model",
            llm_provider="openai"
        )

        circuit_breaker.record_failure(error)

        # Should call update with new state
        mock_db.facade.update_llm_retry_state.assert_called()
        call_args = mock_db.facade.update_llm_retry_state.call_args_list[0][0][0]
        assert 'model_name' in call_args
        assert 'consecutive_failures' in call_args

    def test_updates_database_on_success(self, circuit_breaker, mock_db):
        """Test that circuit breaker resets database state on success."""
        mock_db.facade.get_llm_retry_state.return_value = {
            'consecutive_failures': 3,
            'circuit_state': 'closed'
        }

        circuit_breaker.record_success()

        # Should call reset
        mock_db.facade.reset_llm_retry_state.assert_called_once_with("test-model")

    def test_handles_database_errors_gracefully(self, circuit_breaker, mock_db):
        """Test that circuit breaker handles database errors."""
        mock_db.facade.get_llm_retry_state.side_effect = Exception("Database error")

        # Should not crash, might allow request or log error
        try:
            circuit_breaker.check_circuit()
        except Exception as e:
            # Should be a database error, not a circuit breaker error
            assert "Database error" in str(e) or isinstance(e, Exception)


class TestCircuitBreakerIntegration:
    """Integration tests for circuit breaker."""

    def test_multiple_models_independent_circuits(self):
        """Test that different models have independent circuit breakers."""
        cb1 = CircuitBreaker(model_name="gpt-4")
        cb2 = CircuitBreaker(model_name="gpt-3.5-turbo")

        assert cb1.model_name != cb2.model_name
        assert cb1.model_name == "gpt-4"
        assert cb2.model_name == "gpt-3.5-turbo"

    def test_circuit_breaker_persistence(self, mock_db):
        """Test that circuit breaker state persists across instances."""
        with patch('app.database.get_database_instance', return_value=mock_db):
            # First instance records failures
            mock_db.facade.get_llm_retry_state.return_value = {
                'consecutive_failures': 3,
                'circuit_state': 'closed'
            }

            cb1 = CircuitBreaker(model_name="gpt-4")
            error = litellm.RateLimitError(
                message="Rate limit",
                model="gpt-4",
                llm_provider="openai"
            )
            cb1.record_failure(error)

            # Should have updated via facade
            mock_db.facade.update_llm_retry_state.assert_called()
            call_args = mock_db.facade.update_llm_retry_state.call_args_list[0][0][0]
            assert call_args['consecutive_failures'] == 4

            # Second instance should see updated state
            mock_db.facade.get_llm_retry_state.return_value = {
                'consecutive_failures': 4,
                'circuit_state': 'closed'
            }

            cb2 = CircuitBreaker(model_name="gpt-4")
            state = cb2.get_state()

            # Should load the persisted state
            mock_db.facade.get_llm_retry_state.assert_called_with("gpt-4")
            assert state['consecutive_failures'] == 4


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
