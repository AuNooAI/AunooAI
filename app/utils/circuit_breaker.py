"""
Circuit breaker pattern for LLM API calls with persistent state.

This module implements the circuit breaker pattern to prevent cascading failures
when LLM APIs are experiencing issues. State is persisted to the database to
survive service restarts.
"""
import logging
from datetime import datetime
from typing import Optional
from enum import Enum

logger = logging.getLogger(__name__)


class CircuitState(Enum):
    """Circuit breaker states."""
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitBreakerOpen(Exception):
    """Raised when circuit breaker is open and blocking requests"""

    def __init__(self, model_name: str, opened_at: Optional[datetime], timeout_seconds: int):
        """
        Initialize CircuitBreakerOpen exception.

        Args:
            model_name: Name of the model whose circuit is open
            opened_at: When the circuit was opened
            timeout_seconds: How long the circuit will remain open
        """
        self.model_name = model_name
        self.opened_at = opened_at
        self.timeout_seconds = timeout_seconds

        message = f"Circuit breaker is OPEN for model '{model_name}'. "
        if opened_at:
            message += f"Opened at {opened_at}. "
        message += f"Will retry after {timeout_seconds} seconds timeout."

        super().__init__(message)


class CircuitBreaker:
    """
    Circuit breaker for LLM API calls with persistent state.

    The circuit has three states:
    - CLOSED: Normal operation, all requests allowed
    - OPEN: Too many failures, blocking all requests
    - HALF_OPEN: Testing if service has recovered
    """

    # Configuration constants
    FAILURE_THRESHOLD = 5  # Open circuit after N consecutive failures
    TIMEOUT_DURATION = 300  # Keep circuit open for 5 minutes (seconds)
    HALF_OPEN_MAX_ATTEMPTS = 3  # Allow N attempts in half-open state

    def __init__(self, model_name: str):
        """
        Initialize circuit breaker for a specific model.

        Args:
            model_name: Name of the LLM model to protect
        """
        self.model_name = model_name
        self.db = None  # Lazy loaded to avoid circular imports

    def _get_db(self):
        """Lazy load database instance to avoid circular imports"""
        if self.db is None:
            from app.database import get_database_instance
            self.db = get_database_instance()
        return self.db

    def get_state(self) -> dict:
        """
        Get current circuit state from database.

        Returns:
            dict: Circuit state data with keys:
                - circuit_state: 'closed', 'open', or 'half_open'
                - consecutive_failures: Number of consecutive failures
                - circuit_opened_at: Timestamp when circuit opened (or None)
        """
        db = self._get_db()
        state = db.facade.get_llm_retry_state(self.model_name)

        if not state:
            # Initialize default state
            return {
                'circuit_state': 'closed',
                'consecutive_failures': 0,
                'circuit_opened_at': None
            }

        return state

    def check_circuit(self) -> bool:
        """
        Check if circuit allows request to proceed.

        Returns:
            bool: True if request should proceed

        Raises:
            CircuitBreakerOpen: If circuit is open and timeout hasn't expired
        """
        state = self.get_state()
        circuit_state = state['circuit_state']
        consecutive_failures = state['consecutive_failures']
        circuit_opened_at = state.get('circuit_opened_at')

        # CLOSED state - allow all requests
        if circuit_state == 'closed':
            logger.debug(
                f"✅ Circuit CLOSED for {self.model_name} - allowing request "
                f"(failures: {consecutive_failures}/{self.FAILURE_THRESHOLD})"
            )
            if consecutive_failures >= self.FAILURE_THRESHOLD:
                # Threshold exceeded - open circuit
                logger.warning(
                    f"⚠️ Circuit breaker threshold reached for {self.model_name} "
                    f"({consecutive_failures}/{self.FAILURE_THRESHOLD} failures)"
                )
                self._open_circuit()
                raise CircuitBreakerOpen(
                    self.model_name,
                    datetime.utcnow(),
                    self.TIMEOUT_DURATION
                )
            return True

        # OPEN state - check if timeout has elapsed
        if circuit_state == 'open':
            if circuit_opened_at:
                opened_time = circuit_opened_at
                if isinstance(opened_time, str):
                    opened_time = datetime.fromisoformat(opened_time)

                elapsed = (datetime.utcnow() - opened_time).total_seconds()
                remaining = self.TIMEOUT_DURATION - elapsed

                if elapsed >= self.TIMEOUT_DURATION:
                    # Timeout elapsed - enter half-open state
                    logger.info(
                        f"🟡 Circuit breaker timeout elapsed for {self.model_name} "
                        f"({elapsed:.0f}s >= {self.TIMEOUT_DURATION}s) - entering HALF-OPEN state"
                    )
                    self._half_open_circuit()
                    return True
                else:
                    logger.debug(
                        f"🔴 Circuit OPEN for {self.model_name} - blocking request "
                        f"(elapsed: {elapsed:.0f}s, remaining: {remaining:.0f}s)"
                    )

            # Circuit still open
            raise CircuitBreakerOpen(
                self.model_name,
                circuit_opened_at,
                self.TIMEOUT_DURATION
            )

        # HALF_OPEN state - allow limited requests
        if circuit_state == 'half_open':
            logger.info(
                f"🟡 Circuit HALF-OPEN for {self.model_name} - allowing test request "
                f"(failures: {consecutive_failures})"
            )
            return True

        return False

    def record_success(self):
        """
        Record successful request - close circuit.

        This resets the failure counter and closes the circuit,
        allowing normal operation to resume.
        """
        logger.info(f"✅ Circuit breaker: Success for {self.model_name} - closing circuit")
        db = self._get_db()
        db.facade.reset_llm_retry_state(self.model_name)

    def record_failure(self, error: Exception):
        """
        Record failed request - may open circuit.

        Args:
            error: The exception that caused the failure
        """
        state = self.get_state()
        consecutive_failures = state['consecutive_failures'] + 1

        logger.warning(
            f"⚠️ Circuit breaker: Failure {consecutive_failures} for {self.model_name}"
        )

        db = self._get_db()
        db.facade.update_llm_retry_state({
            'model_name': self.model_name,
            'consecutive_failures': consecutive_failures,
            'last_failure_time': datetime.utcnow(),
            'metadata': {
                'last_error': error.__class__.__name__,
                'last_error_message': str(error)
            }
        })

        # Check if we should open circuit
        if consecutive_failures >= self.FAILURE_THRESHOLD:
            self._open_circuit()

    def _open_circuit(self):
        """Open the circuit breaker to block requests"""
        logger.error(f"🔴 Circuit breaker OPENED for {self.model_name}")

        db = self._get_db()
        db.facade.update_llm_retry_state({
            'model_name': self.model_name,
            'circuit_state': 'open',
            'circuit_opened_at': datetime.utcnow()
        })

    def _half_open_circuit(self):
        """Enter half-open state to test recovery"""
        logger.info(f"🟡 Circuit breaker HALF-OPEN for {self.model_name}")

        db = self._get_db()
        db.facade.update_llm_retry_state({
            'model_name': self.model_name,
            'circuit_state': 'half_open'
        })

    def reset(self):
        """Manually reset the circuit breaker (for admin use)"""
        logger.info(f"🔄 Circuit breaker manually RESET for {self.model_name}")
        db = self._get_db()
        db.facade.reset_llm_retry_state(self.model_name)
