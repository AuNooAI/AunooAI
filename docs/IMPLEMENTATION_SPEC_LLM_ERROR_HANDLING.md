# Implementation Specification: LiteLLM Exception Handling & Bail-Out Policy

**Version:** 1.3 (Relevance Score Persistence Added)
**Date:** 2025-01-18
**Status:** Ready for Implementation
**Priority:** Critical

---

## 🔧 CRITICAL FIXES APPLIED

### Version 1.3 (Latest)

**NEW: Relevance Score Persistence Enhancement**

This version adds critical fixes to ensure relevance scores are ALWAYS saved to the database, even when articles are not enriched or when errors occur during processing.

**4 Additional Fixes Added to Phase 2:**

1. **Exception Handling in Quick Relevance Check**
   - **Issue**: When quick relevance check fails, articles continue to enrichment with score=0.0, wasting API calls
   - **Fix**: Save article with error status and skip enrichment when relevance check fails
   - **Impact**: Prevents wasted enrichment costs on articles where we couldn't calculate relevance

2. **Early-Filter Missing Score Fields**
   - **Issue**: Early-filtered articles only save `keyword_relevance_score`, leaving other fields NULL
   - **Fix**: Populate all three score fields (topic_alignment, keyword_relevance, confidence) from relevance result
   - **Impact**: Database has complete relevance data for all processed articles

3. **RelevanceCalculator Return Structure**
   - **Issue**: Need to verify all score fields are returned from relevance calculation
   - **Fix**: Ensure return dictionary includes topic_alignment_score, keyword_relevance_score, and confidence_score
   - **Impact**: Downstream code can extract individual scores, not just combined average

4. **Final Relevance Calculation Fallback**
   - **Issue**: If final relevance calculation fails after enrichment, enriched data could be lost
   - **Fix**: Add try/except with fallback scores to preserve enrichment work even if relevance fails
   - **Impact**: Never lose expensive enrichment work (bias data, scraped content, LLM analysis)

**Implementation Time Impact:** Phase 2 increased from 1 hour to 1.5 hours (+30 minutes)

---

### Version 1.2

This specification has been reviewed by spec-implementation-reviewer agent and **3 additional critical issues** have been addressed:

1. **Complete Database Facade Implementation (Phase 0)**
   - **Issue**: Phase 0 only had method signatures, not complete implementation code
   - **Fix**: Added full implementation code for all required facade methods with error handling
   - **Impact**: Developers can now implement Phase 0 without guessing implementation details

2. **Job ID Tracking Throughout Pipeline**
   - **Issue**: Missing mechanism for generating and passing job_id for WebSocket notifications
   - **Fix**: Added job_id generation, tracking, and passing through the entire processing pipeline
   - **Impact**: WebSocket notifications will have valid job_id, enabling proper client subscription

3. **Incomplete LiteLLM Exception Coverage**
   - **Issue**: Missing several LiteLLM exceptions (BudgetExceededError, InvalidRequestError, JSONSchemaValidationError)
   - **Fix**: Added all missing exceptions to classification system with proper severity levels
   - **Impact**: All possible LiteLLM errors now handled with appropriate strategies

### Version 1.1

This specification has been reviewed and **5 critical issues** have been fixed:

### ✅ Fixed Issues

1. **Async/Sync Event Loop Conflicts** (Lines 429, 447)
   - **Problem**: Used `asyncio.run()` inside synchronous methods, which causes `RuntimeError: asyncio.run() cannot be called from a running event loop`
   - **Fix**: Added `_retry_sync()` method that uses `time.sleep()` instead of async sleep
   - **Impact**: Prevents runtime crashes when called from async contexts

2. **Missing Database Facade Methods**
   - **Problem**: Referenced methods `log_processing_error()` and `update_article_status()` don't exist in `DatabaseQueryFacade`
   - **Fix**: Added complete specifications for required methods and marked them as TODO for Phase 0
   - **Impact**: Clear implementation requirements before Phase 1

3. **Incorrect WebSocket Manager Usage**
   - **Problem**: Spec referenced `ConnectionManager.broadcast()` which doesn't exist
   - **Fix**: Updated to use actual WebSocket manager from `app/routes/websocket_routes.py` with `send_job_update()` method
   - **Impact**: WebSocket notifications will actually work

4. **No Persistent Retry State**
   - **Problem**: Retry state wouldn't survive service restarts
   - **Fix**: Added complete database schema and facade methods for `llm_retry_state` table
   - **Impact**: Circuit breaker pattern works across restarts

5. **Missing Circuit Breaker Pattern**
   - **Problem**: No mechanism to prevent cascading failures during API outages
   - **Fix**: Added complete `CircuitBreaker` class implementation with 3-state pattern (closed/open/half-open)
   - **Impact**: Prevents expensive API calls during outages, enables graceful degradation

### 📋 New Requirements

- **Phase 0 Added**: Database schema and facade methods must be implemented first
- **Implementation Time Updated**: Total time now 5.5-7 hours (was 3-4 hours)
- **Testing Requirements**: Added circuit breaker tests

---

## Executive Summary

This specification addresses critical gaps in LLM error handling across the AunooAI article processing pipeline. Currently, all LLM operations use generic `Exception` catches with string-based error detection, leading to poor error recovery and inability to distinguish between fatal errors (authentication failures) and recoverable errors (rate limits, timeouts).

**Key Changes:**
1. Replace generic exception handling with LiteLLM-specific exception types
2. Implement bail-out policy for fatal errors (AuthenticationError)
3. Add retry logic with exponential backoff for transient errors
4. Define error severity classification system
5. Improve error reporting and user notifications
6. **NEW:** Ensure relevance scores are ALWAYS saved, even for non-enriched articles

**Impact:**
- Prevents pipeline failures from propagating silently
- Enables intelligent retry strategies
- Stops processing immediately on unrecoverable errors (invalid API keys)
- Improves system resilience and cost efficiency
- **NEW:** Preserves all relevance scoring data for analysis and debugging
- **NEW:** Prevents wasted API calls when relevance calculation fails

---

## Prerequisites and Dependencies

### Required Versions
- **LiteLLM**: >=1.0.0 (tested with 1.x.x series)
- **Python**: 3.8+
- **Required Packages**:
  - `litellm` - LLM abstraction layer with exception types
  - `asyncio` - Async/await support for retry logic
  - `typing` - Type hints for error classification

### LiteLLM Exception Support
This implementation relies on LiteLLM's standardized exception types introduced in version 1.0+. Verify your LiteLLM version supports:
- `litellm.AuthenticationError`
- `litellm.RateLimitError`
- `litellm.ContextWindowExceededError`
- `litellm.BadRequestError`
- `litellm.ServiceUnavailableError`
- `litellm.Timeout`
- `litellm.APIConnectionError`
- `litellm.APIError`

### Compatibility Notes
- Pin LiteLLM version in `requirements.txt` to prevent breaking changes
- Monitor LiteLLM release notes for exception type changes
- Test with your specific LLM providers (OpenAI, Anthropic, etc.)

---

## Current State Analysis

### Problem Statement

**Finding 1: No LiteLLM-Specific Exception Handling**
- Zero imports of LiteLLM exception types across entire codebase
- All LLM calls use `except Exception as e` (generic catch-all)
- String-based error detection (`"rate limit" in error_message.lower()`) is fragile and unreliable

**Finding 2: No Bail-Out Behavior**
- Individual article failures → logged, processing continues
- Authentication failures → treated same as rate limits
- Unknown errors → processing continues with degraded data
- No mechanism to stop pipeline on fatal errors

**Finding 3: Relevance Score Confusion (Resolved)**
- Three distinct scores exist: `topic_alignment_score`, `keyword_relevance_score`, `confidence_score`
- All are stored separately in database and displayed in UI
- No bug found - system working as designed
- Action: Document score meanings for users

### Affected Files

| File | Current Issue | Lines Affected |
|------|---------------|----------------|
| `app/ai_models.py` | Generic Exception catch | 568-629, 127-145, 168-196 |
| `app/relevance.py` | Generic Exception catch, raises custom error | 143-250 |
| `app/analyzers/article_analyzer.py` | Generic Exception catch | 76-85, 150-180 |
| `app/services/automated_ingest_service.py` | Generic Exception processing | 713-732, 1056-1097 |
| `app/bulk_research.py` | Uses ArticleAnalyzer (inherited issue) | Multiple |
| `app/services/auspex_service.py` | Uses ai_model.generate_response() | Multiple |

---

## Technical Design

### 1. Exception Hierarchy

#### 1.1 LiteLLM Exception Types

According to [LiteLLM documentation](https://docs.litellm.ai/docs/exception_mapping):

```python
import litellm

# Exception types (in order of specificity)
litellm.AuthenticationError          # 401 - Invalid API key, auth failure
litellm.RateLimitError               # 429 - Rate limiting
litellm.ContextWindowExceededError   # 400 - Token limit exceeded
litellm.BadRequestError              # 400 - Invalid parameters
litellm.InvalidRequestError          # 400 - Invalid request structure
litellm.BudgetExceededError          # Budget/quota exceeded
litellm.JSONSchemaValidationError    # Response doesn't match expected JSON schema
litellm.ServiceUnavailableError      # 503 - Provider downtime
litellm.Timeout                      # Request timeout
litellm.APIConnectionError           # Network connectivity issues
litellm.APIError                     # General API errors
```

#### 1.2 Error Severity Classification

Create new file `app/exceptions.py`:

```python
"""
Exception severity classification for error handling strategy
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
    """Classifies LiteLLM exceptions by severity"""

    # Fatal errors - must stop processing
    FATAL_EXCEPTIONS: List[Type[Exception]] = [
        litellm.AuthenticationError,  # Invalid API key - can't recover
        litellm.BudgetExceededError,  # Budget/quota exceeded - can't continue
    ]

    # Recoverable errors - retry with backoff
    RECOVERABLE_EXCEPTIONS: List[Type[Exception]] = [
        litellm.RateLimitError,        # Wait and retry
        litellm.Timeout,                # Network timeout - retry
        litellm.APIConnectionError,     # Network issue - retry
    ]

    # Skippable errors - skip this item, continue
    SKIPPABLE_EXCEPTIONS: List[Type[Exception]] = [
        litellm.ContextWindowExceededError,  # Content too large
        litellm.BadRequestError,              # Invalid input
        litellm.InvalidRequestError,          # Invalid request structure
        litellm.JSONSchemaValidationError,    # Response validation failed
    ]

    # Degraded errors - try fallback
    DEGRADED_EXCEPTIONS: List[Type[Exception]] = [
        litellm.ServiceUnavailableError,  # Provider down - try fallback
        litellm.APIError,                  # Generic API error - try fallback
    ]

    @classmethod
    def classify(cls, exception: Exception) -> ErrorSeverity:
        """Classify an exception by severity"""
        if isinstance(exception, tuple(cls.FATAL_EXCEPTIONS)):
            return ErrorSeverity.FATAL
        elif isinstance(exception, tuple(cls.RECOVERABLE_EXCEPTIONS)):
            return ErrorSeverity.RECOVERABLE
        elif isinstance(exception, tuple(cls.SKIPPABLE_EXCEPTIONS)):
            return ErrorSeverity.SKIPPABLE
        elif isinstance(exception, tuple(cls.DEGRADED_EXCEPTIONS)):
            return ErrorSeverity.DEGRADED
        else:
            # Unknown errors are fatal (fail-safe)
            return ErrorSeverity.FATAL

    @classmethod
    def should_bail_out(cls, exception: Exception) -> bool:
        """Determine if exception requires immediate pipeline stop"""
        return cls.classify(exception) == ErrorSeverity.FATAL


class PipelineError(Exception):
    """Base exception for pipeline errors with severity"""

    def __init__(self, message: str, severity: ErrorSeverity,
                 original_exception: Exception = None):
        super().__init__(message)
        self.severity = severity
        self.original_exception = original_exception
```

### 2. Retry Logic with Exponential Backoff

Create new file `app/utils/retry.py`:

```python
"""
Retry utilities with exponential backoff for transient errors
"""
import asyncio
import logging
from typing import Callable, Any, Optional, Type, Tuple
from functools import wraps
import random

logger = logging.getLogger(__name__)


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
        self.max_attempts = max_attempts
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.exponential_base = exponential_base
        self.jitter = jitter

    def get_delay(self, attempt: int) -> float:
        """Calculate delay for given attempt number"""
        # Exponential backoff: base_delay * (exponential_base ^ attempt)
        delay = self.base_delay * (self.exponential_base ** attempt)

        # Cap at max_delay
        delay = min(delay, self.max_delay)

        # Add jitter to prevent thundering herd
        if self.jitter:
            delay = delay * (0.5 + random.random())

        return delay


async def retry_with_backoff(
    func: Callable,
    *args,
    retryable_exceptions: Tuple[Type[Exception], ...] = (Exception,),
    config: Optional[RetryConfig] = None,
    **kwargs
) -> Any:
    """
    Retry async function with exponential backoff

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
                return await func(*args, **kwargs)
            else:
                # Run sync function in executor
                loop = asyncio.get_event_loop()
                return await loop.run_in_executor(None, func, *args, **kwargs)

        except retryable_exceptions as e:
            last_exception = e

            if attempt < config.max_attempts - 1:
                delay = config.get_delay(attempt)
                logger.warning(
                    f"Attempt {attempt + 1}/{config.max_attempts} failed: {e}. "
                    f"Retrying in {delay:.2f}s..."
                )
                await asyncio.sleep(delay)
            else:
                logger.error(
                    f"All {config.max_attempts} attempts failed. Last error: {e}"
                )

        except Exception as e:
            # Non-retryable exception - raise immediately
            logger.error(f"Non-retryable exception on attempt {attempt + 1}: {e}")
            raise

    # All retries exhausted
    raise last_exception


def retry_on_rate_limit(max_attempts: int = 3):
    """
    Decorator for retrying on rate limit errors

    Usage:
        @retry_on_rate_limit(max_attempts=3)
        async def my_llm_call():
            ...
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
```

### 3. Core Implementation Changes

#### 3.1 Update `app/ai_models.py`

**Location:** Lines 3-8 (imports)

**Current:**
```python
from litellm import Router
from litellm import completion
import litellm
```

**New:**
```python
from litellm import Router, completion
import litellm
from litellm import (
    RateLimitError,
    AuthenticationError,
    BadRequestError,
    InvalidRequestError,
    BudgetExceededError,
    JSONSchemaValidationError,
    ContextWindowExceededError,
    ServiceUnavailableError,
    Timeout,
    APIConnectionError,
    APIError
)
from app.exceptions import LLMErrorClassifier, ErrorSeverity, PipelineError
from app.utils.retry import retry_with_backoff, RetryConfig
```

**Location:** Lines 568-629 (`generate_response` method)

**Current:**
```python
def generate_response(self, messages, _is_fallback=False, _attempted_models=None):
    try:
        response = self.router.completion(
            model=self.model_name,
            messages=messages,
            temperature=self.temperature,
            max_tokens=self.max_tokens
        )
        content = response.choices[0].message.content
        return content

    except Exception as e:  # ❌ Generic catch
        error_message = str(e)
        logger.error(f"❌ Error generating response with {self.model_name}: {error_message}")

        # String-based error detection
        is_context_window_error = "context length" in error_message.lower()
        # ...
```

**New:**
```python
def generate_response(self, messages, _is_fallback=False, _attempted_models=None):
    """
    Generate LLM response with proper exception handling

    Raises:
        PipelineError: For fatal errors requiring pipeline stop
        Returns error message string for recoverable/skippable errors
    """
    try:
        response = self.router.completion(
            model=self.model_name,
            messages=messages,
            temperature=self.temperature,
            max_tokens=self.max_tokens
        )
        content = response.choices[0].message.content
        return content

    # FATAL ERRORS - Must stop processing
    except AuthenticationError as e:
        logger.error(f"🚨 FATAL: Authentication failed for {self.model_name}: {e}")
        logger.error("Check API key configuration and restart service")
        raise PipelineError(
            f"Authentication failed - invalid API key for {self.model_name}",
            severity=ErrorSeverity.FATAL,
            original_exception=e
        )

    except BudgetExceededError as e:
        logger.error(f"🚨 FATAL: Budget/quota exceeded for {self.model_name}: {e}")
        logger.error("API budget or quota limit reached - cannot continue processing")
        raise PipelineError(
            f"Budget exceeded for {self.model_name} - check account limits",
            severity=ErrorSeverity.FATAL,
            original_exception=e
        )

    # RECOVERABLE ERRORS - Retry with backoff
    except RateLimitError as e:
        logger.warning(f"⏸️ Rate limit hit for {self.model_name}: {e}")

        # Try retry with exponential backoff
        # Use sync retry helper to avoid event loop conflicts
        try:
            config = RetryConfig(max_attempts=3, base_delay=2.0)
            return self._retry_sync(
                self._generate_with_retry,
                messages,
                retryable_exceptions=(RateLimitError,),
                config=config
            )
        except RateLimitError as retry_error:
            # All retries exhausted - try fallback model
            logger.error(f"Rate limit retries exhausted for {self.model_name}")
            return self._try_fallback_model(messages, _attempted_models,
                                           "Rate limit exceeded")

    except (Timeout, APIConnectionError) as e:
        logger.warning(f"🔌 Network error for {self.model_name}: {e}")

        # Try retry once
        # Use sync retry helper to avoid event loop conflicts
        try:
            config = RetryConfig(max_attempts=2, base_delay=1.0)
            return self._retry_sync(
                self._generate_with_retry,
                messages,
                retryable_exceptions=(Timeout, APIConnectionError),
                config=config
            )
        except (Timeout, APIConnectionError):
            # Retry failed - try fallback
            return self._try_fallback_model(messages, _attempted_models,
                                           f"Network error: {str(e)}")

    # SKIPPABLE ERRORS - Skip this request
    except ContextWindowExceededError as e:
        logger.warning(f"📏 Content too large for {self.model_name}: {e}")

        # Try fallback with smaller context window
        fallback_result = self._try_fallback_model(
            messages, _attempted_models,
            "Content too large for context window"
        )

        if fallback_result:
            return fallback_result

        # No fallback available - return error message
        return (
            f"Error: Content exceeds maximum length for {self.model_name}. "
            "Please reduce content size or split into smaller chunks."
        )

    except BadRequestError as e:
        logger.error(f"❌ Invalid request for {self.model_name}: {e}")
        return (
            f"Error: Invalid request parameters for {self.model_name}. "
            f"Details: {str(e)}"
        )

    except InvalidRequestError as e:
        logger.error(f"❌ Invalid request structure for {self.model_name}: {e}")
        return (
            f"Error: Invalid request format for {self.model_name}. "
            f"Details: {str(e)}"
        )

    except JSONSchemaValidationError as e:
        logger.error(f"❌ Response validation failed for {self.model_name}: {e}")
        # This is a response format issue - try fallback or return error
        fallback_result = self._try_fallback_model(
            messages, _attempted_models,
            f"Response validation failed: {str(e)}"
        )

        if fallback_result:
            return fallback_result

        return (
            f"Error: Response from {self.model_name} didn't match expected format. "
            f"Details: {str(e)}"
        )

    # DEGRADED ERRORS - Try fallback
    except (ServiceUnavailableError, APIError) as e:
        logger.warning(f"⚠️ Service error for {self.model_name}: {e}")

        # Try fallback immediately
        fallback_result = self._try_fallback_model(
            messages, _attempted_models,
            f"Service unavailable: {str(e)}"
        )

        if fallback_result:
            return fallback_result

        # No fallback - return degraded response
        return (
            f"Error: {self.model_name} is temporarily unavailable. "
            "Please try again later."
        )

    # UNKNOWN ERRORS - Treat as fatal
    except Exception as e:
        logger.error(f"🚨 Unexpected error in {self.model_name}: {e}")
        logger.exception("Full traceback:")

        # Unknown errors are fatal
        raise PipelineError(
            f"Unexpected LLM error: {str(e)}",
            severity=ErrorSeverity.FATAL,
            original_exception=e
        )

def _generate_with_retry(self, messages):
    """Helper for retry logic - wraps completion call"""
    response = self.router.completion(
        model=self.model_name,
        messages=messages,
        temperature=self.temperature,
        max_tokens=self.max_tokens
    )
    return response.choices[0].message.content

def _retry_sync(self, func, messages, retryable_exceptions, config):
    """
    Synchronous retry helper to avoid asyncio.run() event loop conflicts.

    This method implements retry logic without using asyncio.run(), which would
    fail if called from an async context (RuntimeError: asyncio.run() cannot be
    called from a running event loop).
    """
    import time
    last_exception = None

    for attempt in range(config.max_attempts):
        try:
            return func(messages)
        except retryable_exceptions as e:
            last_exception = e

            if attempt < config.max_attempts - 1:
                delay = config.get_delay(attempt)
                logger.warning(
                    f"Attempt {attempt + 1}/{config.max_attempts} failed: {e}. "
                    f"Retrying in {delay:.2f}s..."
                )
                time.sleep(delay)  # Use time.sleep() not asyncio.sleep() for sync
            else:
                logger.error(
                    f"All {config.max_attempts} attempts failed. Last error: {e}"
                )
        except Exception as e:
            # Non-retryable exception - raise immediately
            logger.error(f"Non-retryable exception on attempt {attempt + 1}: {e}")
            raise

    # All retries exhausted
    raise last_exception

def _try_fallback_model(self, messages, attempted_models, reason, _is_fallback=False):
    """Try fallback model if available"""
    if self.fallback_models and not _is_fallback:
        # Track attempted models
        if attempted_models is None:
            attempted_models = [self.model_name]

        # Try each fallback
        for fallback_model in self.fallback_models:
            if fallback_model not in attempted_models:
                logger.info(f"🔄 Trying fallback model: {fallback_model}")

                try:
                    # Create temporary model instance
                    fallback_instance = LiteLLMModel(fallback_model)
                    return fallback_instance.generate_response(
                        messages,
                        _is_fallback=True,
                        _attempted_models=attempted_models + [fallback_model]
                    )
                except Exception as fallback_error:
                    logger.warning(f"Fallback {fallback_model} also failed: {fallback_error}")
                    continue

    return None
```

#### 3.2 Update `app/relevance.py`

**Location:** Lines 1-10 (imports)

**Add:**
```python
import litellm
from litellm import (
    RateLimitError,
    AuthenticationError,
    ContextWindowExceededError,
    ServiceUnavailableError,
    Timeout
)
from app.exceptions import PipelineError, ErrorSeverity
```

**Location:** Lines 143-250 (`analyze_relevance` method)

**Current:**
```python
def analyze_relevance(self, title, source, content, topic, keywords, topic_description=None):
    try:
        messages = self.prompt_templates.format_relevance_analysis_prompt(...)
        response_text = self.ai_model.generate_response(messages)
        # ... parse JSON
        return validated_result

    except Exception as e:
        logger.error(f"Error during relevance analysis: {str(e)}")
        raise RelevanceCalculatorError(f"Relevance analysis failed: {str(e)}")
```

**New:**
```python
def analyze_relevance(self, title, source, content, topic, keywords, topic_description=None):
    """
    Analyze article relevance with proper error handling

    Returns:
        Dict with relevance scores, or default scores on skippable errors

    Raises:
        RelevanceCalculatorError: For recoverable/degraded errors
        PipelineError: For fatal errors (authentication)
    """
    try:
        messages = self.prompt_templates.format_relevance_analysis_prompt(...)
        response_text = self.ai_model.generate_response(messages)

        # Parse JSON response
        result = json.loads(json_str)
        validated_result = self._validate_result(result)
        return validated_result

    # Fatal errors - let PipelineError propagate up
    except PipelineError:
        raise  # Don't catch, let caller handle

    # Context too large - return default low scores
    except ContextWindowExceededError as e:
        logger.warning(f"Content too large for relevance analysis: {e}")
        return self._default_scores(
            explanation=f"Content exceeds maximum length: {str(e)}"
        )

    # Rate limits - convert to recoverable error
    except RateLimitError as e:
        logger.error(f"Rate limit during relevance analysis: {e}")
        raise RelevanceCalculatorError(
            f"Rate limit exceeded - please retry: {str(e)}"
        )

    # Service errors - convert to recoverable error
    except (ServiceUnavailableError, Timeout) as e:
        logger.error(f"Service error during relevance analysis: {e}")
        raise RelevanceCalculatorError(
            f"Service temporarily unavailable: {str(e)}"
        )

    # JSON parsing errors - return default scores
    except (json.JSONDecodeError, ValueError, KeyError) as e:
        logger.error(f"Failed to parse LLM response: {e}")
        logger.error(f"Response text: {response_text[:500]}")
        return self._default_scores(
            explanation=f"Invalid LLM response format: {str(e)}"
        )

    # Other exceptions - treat as recoverable
    except Exception as e:
        logger.error(f"Unexpected error in relevance analysis: {e}")
        logger.exception("Full traceback:")
        raise RelevanceCalculatorError(f"Unexpected error: {str(e)}")

def _default_scores(self, explanation: str) -> dict:
    """Return default scores when analysis fails"""
    return {
        "topic_alignment_score": 0.0,
        "keyword_relevance_score": 0.0,
        "confidence_score": 0.0,
        "overall_match_explanation": explanation,
        "category": "Unknown",
        "extracted_topics": [],
        "extracted_keywords": [],
        "relevance_score": 0.0
    }
```

#### 3.3 Update `app/analyzers/article_analyzer.py`

**Location:** Top of file (imports)

**Add:**
```python
import litellm
from litellm import ContextWindowExceededError, RateLimitError
from app.exceptions import PipelineError
```

**Location:** Lines 76-85 and similar LLM-calling methods

**Current:**
```python
def extract_title(self, article_text: str):
    try:
        title_response = self.ai_model.generate_response(prompts)
        # ...
    except Exception as e:
        raise ArticleAnalyzerError(f"Failed to extract title: {str(e)}")
```

**New:**
```python
def extract_title(self, article_text: str):
    """
    Extract title from article with error handling

    Returns:
        Extracted title string, or None on skippable errors

    Raises:
        ArticleAnalyzerError: For recoverable errors
        PipelineError: For fatal errors
    """
    try:
        title_response = self.ai_model.generate_response(prompts)
        # ... parse response
        return title

    # Fatal errors - propagate
    except PipelineError:
        raise

    # Content too large - return None (use fallback title)
    except ContextWindowExceededError as e:
        logger.warning(f"Content too large for title extraction: {e}")
        return None

    # Rate limits - convert to recoverable error
    except RateLimitError as e:
        logger.error(f"Rate limit during title extraction: {e}")
        raise ArticleAnalyzerError(f"Rate limit exceeded: {str(e)}")

    # Other errors
    except Exception as e:
        logger.error(f"Title extraction failed: {e}")
        raise ArticleAnalyzerError(f"Failed to extract title: {str(e)}")
```

**Apply same pattern to:**
- `analyze_content()` - Return None or partial data on ContextWindowExceededError
- `summarize_content()` - Return None on ContextWindowExceededError
- Other LLM-calling methods

#### 3.4 Update `app/services/automated_ingest_service.py`

**Location:** Top of file (imports)

**Add:**
```python
import litellm
from litellm import RateLimitError, AuthenticationError, ContextWindowExceededError
from app.exceptions import PipelineError, LLMErrorClassifier, ErrorSeverity
```

**Location:** Lines 713-732 (LLM analysis in `_process_single_article_async`)

**Current:**
```python
try:
    enriched_article = await asyncio.wait_for(
        self._analyze_article_content_async(enriched_article, topic),
        timeout=60
    )
except asyncio.TimeoutError:
    logger.warning(f"LLM analysis timed out for {article_uri}")
    enriched_article["analysis_error"] = "LLM analysis timed out"
except Exception as e:
    logger.error(f"LLM analysis failed for {article_uri}: {e}")
    enriched_article["analysis_error"] = str(e)
```

**New:**
```python
try:
    enriched_article = await asyncio.wait_for(
        self._analyze_article_content_async(enriched_article, topic),
        timeout=60
    )

# Fatal errors - re-raise to stop batch
except PipelineError as e:
    if e.severity == ErrorSeverity.FATAL:
        logger.error(f"🚨 FATAL ERROR in article {article_uri}: {e}")
        raise  # Stop entire batch processing
    else:
        # Non-fatal pipeline error - log and continue
        logger.warning(f"Pipeline error for {article_uri}: {e}")
        enriched_article["analysis_error"] = str(e)

except asyncio.TimeoutError:
    logger.warning(f"⏱️ LLM analysis timed out for {article_uri}")
    enriched_article["analysis_error"] = "LLM analysis timed out"

except ContextWindowExceededError as e:
    logger.warning(f"📏 Article too large for analysis: {article_uri}")
    enriched_article["analysis_error"] = f"Content too large: {str(e)}"
    # Mark for skipping
    return {
        "status": "skipped",
        "uri": article_uri,
        "reason": "content_too_large",
        "error": str(e)
    }

except RateLimitError as e:
    logger.error(f"⏸️ Rate limit hit during analysis: {article_uri}")
    enriched_article["analysis_error"] = f"Rate limit: {str(e)}"
    # Could implement pause/retry here

except Exception as e:
    logger.error(f"❌ LLM analysis failed for {article_uri}: {e}")
    enriched_article["analysis_error"] = str(e)
```

**Location:** Lines 1056-1097 (batch processing)

**Current:**
```python
for result in batch_results:
    if isinstance(result, Exception):
        results["errors"].append(str(result))
    elif isinstance(result, dict):
        # Process result
```

**New:**
```python
for result in batch_results:
    # Check for fatal errors
    if isinstance(result, PipelineError):
        if result.severity == ErrorSeverity.FATAL:
            logger.error(f"🚨 FATAL ERROR in batch - stopping: {result}")
            # Stop processing remaining batches
            raise result
        else:
            # Non-fatal pipeline error
            results["errors"].append({
                "type": "pipeline_error",
                "severity": result.severity.value,
                "message": str(result)
            })

    elif isinstance(result, AuthenticationError):
        logger.error(f"🚨 Authentication failed - STOPPING BATCH: {result}")
        raise PipelineError(
            f"Authentication error: {str(result)}",
            severity=ErrorSeverity.FATAL,
            original_exception=result
        )

    elif isinstance(result, RateLimitError):
        logger.warning(f"⏸️ Rate limit in batch: {result}")
        results["rate_limited"] += 1
        results["errors"].append({
            "type": "rate_limit",
            "message": str(result)
        })

    elif isinstance(result, ContextWindowExceededError):
        logger.warning(f"⏭️ Article skipped (too large): {result}")
        results["skipped"] += 1

    elif isinstance(result, Exception):
        logger.error(f"❌ Unexpected error in batch: {result}")
        results["errors"].append({
            "type": "unexpected",
            "message": str(result)
        })

    elif isinstance(result, dict):
        # Process successful result
        if result.get("status") == "success":
            results["saved"] += 1
            results["vector_indexed"] += 1
            results["quality_passed"] += 1
        elif result.get("status") == "skipped":
            results["skipped"] += 1
        # ... rest of processing
```

---

## Database Integration Patterns

All database operations in this implementation must use the project's database facade pattern to maintain consistency with existing codebase patterns.

### Using Database Facade

```python
from app.database import get_database_instance

# Get database instance
db = get_database_instance()

# All database operations use facade methods
db.facade.method_name(...)  # Note: Most facade methods are synchronous
```

### Required Database Facade Methods

**IMPORTANT**: The following methods **DO NOT CURRENTLY EXIST** in `DatabaseQueryFacade` and must be implemented before this specification can be used:

#### 1. Error Logging Method

```python
def log_llm_processing_error(self, params):
    """
    Log LLM processing errors to database for monitoring and debugging.

    Args:
        params: dict containing:
            - article_id: ID of article being processed (optional)
            - error_type: Exception class name (e.g., "RateLimitError")
            - error_message: Error message string
            - severity: Error severity ("fatal", "recoverable", "skippable", "degraded")
            - model_name: LLM model that generated the error
            - retry_count: Number of retry attempts made
            - will_retry: Boolean indicating if retry will be attempted
            - context: JSON string with additional context
            - timestamp: ISO format timestamp

    Returns:
        int: The ID of the inserted error log, or None if logging failed
    """
    from datetime import datetime
    import json

    # Validate required fields
    required_fields = ['error_type', 'error_message', 'severity', 'model_name', 'timestamp']
    missing_fields = [f for f in required_fields if f not in params]
    if missing_fields:
        logger.error(f"Missing required fields for error logging: {missing_fields}")
        return None

    try:
        # Get fresh connection from the pool (property always returns a fresh connection)
        conn = self.connection
        cursor = conn.cursor()

        try:
            # Insert error log
            cursor.execute("""
                INSERT INTO llm_processing_errors
                (article_id, error_type, error_message, severity, model_name,
                 retry_count, will_retry, context, timestamp)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id
            """, (
                params.get('article_id'),
                params['error_type'],
                params['error_message'],
                params['severity'],
                params['model_name'],
                params.get('retry_count', 0),
                params.get('will_retry', False),
                params.get('context', '{}') if isinstance(params.get('context'), str) else json.dumps(params.get('context', {})),
                params['timestamp'] if isinstance(params['timestamp'], str) else params['timestamp'].isoformat()
            ))

            error_id = cursor.fetchone()[0]
            conn.commit()

            logger.info(f"Logged LLM error {error_id}: {params['error_type']} for model {params['model_name']}")
            return error_id

        except Exception as e:
            logger.error(f"Database error while logging LLM processing error: {e}")
            conn.rollback()
            raise

    except Exception as e:
        logger.error(f"Failed to log LLM processing error to database: {e}")
        logger.exception("Full traceback:")
        # Don't raise - logging errors shouldn't break the pipeline
        return None
```

#### 2. Article Status Update Method

```python
def update_article_llm_status(self, params):
    """
    Update article status when LLM processing completes or fails.

    Args:
        params: dict containing:
            - article_id: ID of article
            - llm_status: Status string ("processing", "completed", "error", "skipped")
            - error_type: Error type if status is "error" (optional)
            - error_message: Error message if status is "error" (optional)
            - processing_metadata: JSON string with processing details (optional)

    Returns:
        bool: True if update successful, False otherwise
    """
    from datetime import datetime
    import json

    # Validate required fields
    if 'article_id' not in params or 'llm_status' not in params:
        logger.error("Missing required fields: article_id and llm_status are required")
        return False

    # Validate status value
    valid_statuses = ['processing', 'completed', 'error', 'skipped']
    if params['llm_status'] not in valid_statuses:
        logger.error(f"Invalid llm_status: {params['llm_status']}. Must be one of {valid_statuses}")
        return False

    try:
        # Get fresh connection from the pool (property always returns a fresh connection)
        conn = self.connection
        cursor = conn.cursor()

        try:
            # Build update query dynamically based on provided params
            update_fields = ['llm_status = %s', 'llm_status_updated_at = %s']
            update_values = [params['llm_status'], datetime.utcnow()]

            if 'error_type' in params and params['error_type']:
                update_fields.append('llm_error_type = %s')
                update_values.append(params['error_type'])

            if 'error_message' in params and params['error_message']:
                update_fields.append('llm_error_message = %s')
                update_values.append(params['error_message'])

            if 'processing_metadata' in params and params['processing_metadata']:
                metadata = params['processing_metadata']
                if not isinstance(metadata, str):
                    metadata = json.dumps(metadata)
                update_fields.append('llm_processing_metadata = %s')
                update_values.append(metadata)

            # Add article_id for WHERE clause
            update_values.append(params['article_id'])

            # Execute update
            query = f"""
                UPDATE articles
                SET {', '.join(update_fields)}
                WHERE id = %s
            """

            cursor.execute(query, update_values)
            rows_affected = cursor.rowcount
            conn.commit()

            if rows_affected == 0:
                logger.warning(f"No article found with id {params['article_id']} to update")
                return False

            logger.info(f"Updated article {params['article_id']} LLM status to {params['llm_status']}")
            return True

        except Exception as e:
            logger.error(f"Database error while updating article LLM status: {e}")
            conn.rollback()
            raise

    except Exception as e:
        logger.error(f"Failed to update article LLM status: {e}")
        logger.exception("Full traceback:")
        # Don't raise - status updates shouldn't break the pipeline
        return False
```

#### 3. Retry State Persistence (for Circuit Breaker)

```python
def get_llm_retry_state(self, model_name):
    """
    Get current retry/failure state for a model.

    Args:
        model_name: Name of the LLM model

    Returns:
        dict: Retry state data, or None if no state exists
    """
    try:
        # Get fresh connection from the pool (property always returns a fresh connection)
        conn = self.connection
        cursor = conn.cursor()

        try:
            cursor.execute("""
                SELECT id, model_name, consecutive_failures, last_failure_time,
                       last_success_time, circuit_state, circuit_opened_at,
                       failure_rate, last_updated, metadata
                FROM llm_retry_state
                WHERE model_name = %s
            """, (model_name,))

            row = cursor.fetchone()
            conn.commit()  # Commit read to close transaction

            if not row:
                return None

            # Convert to dict
            return {
                'id': row[0],
                'model_name': row[1],
                'consecutive_failures': row[2],
                'last_failure_time': row[3],
                'last_success_time': row[4],
                'circuit_state': row[5],
                'circuit_opened_at': row[6],
                'failure_rate': row[7],
                'last_updated': row[8],
                'metadata': row[9]
            }

        except Exception as e:
            logger.error(f"Database error while getting LLM retry state: {e}")
            conn.rollback()
            raise

    except Exception as e:
        logger.error(f"Failed to get LLM retry state for {model_name}: {e}")
        return None


def update_llm_retry_state(self, params):
    """
    Update retry/failure state for a model (for circuit breaker pattern).

    Args:
        params: dict with keys:
            - model_name: str (required)
            - consecutive_failures: int (optional)
            - last_failure_time: datetime (optional)
            - last_success_time: datetime (optional)
            - circuit_state: str ('closed', 'open', 'half_open') (optional)
            - circuit_opened_at: datetime (optional)
            - failure_rate: float (optional)
            - metadata: dict (optional)

    Returns:
        bool: True if update successful, False otherwise
    """
    from datetime import datetime
    import json

    if 'model_name' not in params:
        logger.error("model_name is required for update_llm_retry_state")
        return False

    try:
        # Check if state exists first (using separate connection)
        existing = self.get_llm_retry_state(params['model_name'])

        # Get fresh connection from the pool (property always returns a fresh connection)
        conn = self.connection
        cursor = conn.cursor()

        try:
            if existing:
                # Update existing record
                update_parts = ['last_updated = %s']
                values = [datetime.utcnow()]

                if 'consecutive_failures' in params:
                    update_parts.append('consecutive_failures = %s')
                    values.append(params['consecutive_failures'])

                if 'last_failure_time' in params:
                    update_parts.append('last_failure_time = %s')
                    values.append(params['last_failure_time'])

                if 'last_success_time' in params:
                    update_parts.append('last_success_time = %s')
                    values.append(params['last_success_time'])

                if 'circuit_state' in params:
                    update_parts.append('circuit_state = %s')
                    values.append(params['circuit_state'])

                if 'circuit_opened_at' in params:
                    update_parts.append('circuit_opened_at = %s')
                    values.append(params['circuit_opened_at'])

                if 'failure_rate' in params:
                    update_parts.append('failure_rate = %s')
                    values.append(params['failure_rate'])

                if 'metadata' in params:
                    metadata = params['metadata']
                    if not isinstance(metadata, str):
                        metadata = json.dumps(metadata)
                    update_parts.append('metadata = %s')
                    values.append(metadata)

                values.append(params['model_name'])

                query = f"""
                    UPDATE llm_retry_state
                    SET {', '.join(update_parts)}
                    WHERE model_name = %s
                """

                cursor.execute(query, values)

            else:
                # Insert new record
                cursor.execute("""
                    INSERT INTO llm_retry_state
                    (model_name, consecutive_failures, last_failure_time, last_success_time,
                     circuit_state, circuit_opened_at, failure_rate, metadata, last_updated)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                """, (
                    params['model_name'],
                    params.get('consecutive_failures', 0),
                    params.get('last_failure_time'),
                    params.get('last_success_time'),
                    params.get('circuit_state', 'closed'),
                    params.get('circuit_opened_at'),
                    params.get('failure_rate', 0.0),
                    json.dumps(params.get('metadata', {})) if isinstance(params.get('metadata'), dict) else params.get('metadata', '{}'),
                    datetime.utcnow()
                ))

            conn.commit()
            return True

        except Exception as e:
            logger.error(f"Database error while updating LLM retry state: {e}")
            conn.rollback()
            raise

    except Exception as e:
        logger.error(f"Failed to update LLM retry state: {e}")
        logger.exception("Full traceback:")
        return False


def reset_llm_retry_state(self, model_name):
    """
    Reset retry state for a model (after successful recovery).

    Args:
        model_name: Name of the LLM model

    Returns:
        bool: True if reset successful, False otherwise
    """
    from datetime import datetime

    return self.update_llm_retry_state({
        'model_name': model_name,
        'consecutive_failures': 0,
        'last_success_time': datetime.utcnow(),
        'circuit_state': 'closed',
        'circuit_opened_at': None,
        'failure_rate': 0.0
    })
```

---

## Feature Flags for Safe Rollout

To enable safe, incremental rollout and easy rollback, implement feature flags to control the new error handling behavior.

### Feature Flag Configuration

Create or update the feature flags configuration file:

**File: `app/config/feature_flags.py`**

```python
"""
Feature flags for controlling new functionality rollout.
"""
import os
from typing import Dict, Any

# ============================================================================
# LLM Error Handling Feature Flags
# ============================================================================

# Enable/disable LiteLLM-specific exception handling
# When False: Falls back to legacy string-based error detection
# When True: Uses new LiteLLM exception classes for precise error handling
USE_LITELLM_EXCEPTIONS = os.getenv('USE_LITELLM_EXCEPTIONS', 'true').lower() == 'true'

# Enable/disable circuit breaker pattern
# When False: No circuit breaker protection (all requests attempted)
# When True: Circuit breaker prevents repeated failures to same model
ENABLE_CIRCUIT_BREAKER = os.getenv('ENABLE_CIRCUIT_BREAKER', 'true').lower() == 'true'

# Enable/disable retry logic with exponential backoff
# When False: No automatic retries (fail immediately)
# When True: Retry recoverable errors with exponential backoff
ENABLE_RETRY_LOGIC = os.getenv('ENABLE_RETRY_LOGIC', 'true').lower() == 'true'

# Enable/disable database error logging
# When False: Errors logged only to application logs
# When True: Errors also logged to llm_processing_errors table
ENABLE_ERROR_DB_LOGGING = os.getenv('ENABLE_ERROR_DB_LOGGING', 'true').lower() == 'true'

# Circuit breaker thresholds (can be adjusted without code changes)
CIRCUIT_BREAKER_FAILURE_THRESHOLD = int(os.getenv('CIRCUIT_BREAKER_FAILURE_THRESHOLD', '5'))
CIRCUIT_BREAKER_TIMEOUT_SECONDS = int(os.getenv('CIRCUIT_BREAKER_TIMEOUT_SECONDS', '300'))  # 5 minutes

# Retry configuration
MAX_RETRY_ATTEMPTS = int(os.getenv('MAX_RETRY_ATTEMPTS', '3'))
RETRY_BASE_DELAY_SECONDS = float(os.getenv('RETRY_BASE_DELAY_SECONDS', '2.0'))
RETRY_MAX_DELAY_SECONDS = float(os.getenv('RETRY_MAX_DELAY_SECONDS', '60.0'))


def get_feature_flags() -> Dict[str, Any]:
    """
    Get all feature flags as a dictionary for logging/debugging.

    Returns:
        dict: All feature flag values
    """
    return {
        'USE_LITELLM_EXCEPTIONS': USE_LITELLM_EXCEPTIONS,
        'ENABLE_CIRCUIT_BREAKER': ENABLE_CIRCUIT_BREAKER,
        'ENABLE_RETRY_LOGIC': ENABLE_RETRY_LOGIC,
        'ENABLE_ERROR_DB_LOGGING': ENABLE_ERROR_DB_LOGGING,
        'CIRCUIT_BREAKER_FAILURE_THRESHOLD': CIRCUIT_BREAKER_FAILURE_THRESHOLD,
        'CIRCUIT_BREAKER_TIMEOUT_SECONDS': CIRCUIT_BREAKER_TIMEOUT_SECONDS,
        'MAX_RETRY_ATTEMPTS': MAX_RETRY_ATTEMPTS,
        'RETRY_BASE_DELAY_SECONDS': RETRY_BASE_DELAY_SECONDS,
        'RETRY_MAX_DELAY_SECONDS': RETRY_MAX_DELAY_SECONDS,
    }


def log_feature_flags(logger):
    """
    Log current feature flag configuration at startup.

    Args:
        logger: Logger instance to use
    """
    flags = get_feature_flags()
    logger.info("=" * 60)
    logger.info("LLM Error Handling Feature Flags Configuration")
    logger.info("=" * 60)
    for key, value in flags.items():
        logger.info(f"  {key}: {value}")
    logger.info("=" * 60)
```

### Usage in Exception Handlers

Integrate feature flags in `app/ai_models.py` to allow graceful fallback:

```python
from app.config import feature_flags

class AIModel:
    def generate_response(self, prompt, **kwargs):
        """Generate LLM response with feature-flagged error handling."""

        try:
            # Call LLM API
            response = litellm.completion(...)
            return response

        except Exception as e:
            # Feature-flagged exception handling
            if feature_flags.USE_LITELLM_EXCEPTIONS:
                # NEW: Use LiteLLM exception classes
                return self._handle_litellm_exception(e)
            else:
                # LEGACY: Use string-based error detection
                return self._handle_generic_exception(e)

    def _handle_litellm_exception(self, error):
        """Handle exceptions using new LiteLLM exception classes."""
        from litellm.exceptions import (
            AuthenticationError,
            RateLimitError,
            ContextWindowExceededError,
            APIError,
            ServiceUnavailableError,
            Timeout,
        )

        if isinstance(error, AuthenticationError):
            logger.error(f"🚨 FATAL: Authentication failed for {self.model_name}")
            raise PipelineError(
                f"Authentication failed - check API key for {self.model_name}",
                severity=ErrorSeverity.FATAL,
                original_exception=error
            )

        elif isinstance(error, RateLimitError):
            logger.warning(f"⏱️ RECOVERABLE: Rate limit hit for {self.model_name}")

            # Feature-flagged retry logic
            if feature_flags.ENABLE_RETRY_LOGIC:
                return self._retry_with_backoff(error)
            else:
                raise PipelineError(
                    f"Rate limit exceeded for {self.model_name}",
                    severity=ErrorSeverity.RECOVERABLE,
                    original_exception=error
                )

        # ... other exception types ...

    def _handle_generic_exception(self, error):
        """Legacy exception handling using string detection."""
        error_str = str(error).lower()

        if "authentication" in error_str or "api key" in error_str:
            logger.error(f"🚨 FATAL: Authentication failed (legacy detection)")
            raise PipelineError(
                f"Authentication failed",
                severity=ErrorSeverity.FATAL,
                original_exception=error
            )

        elif "rate limit" in error_str or "quota" in error_str:
            logger.warning(f"⏱️ RECOVERABLE: Rate limit hit (legacy detection)")
            raise PipelineError(
                f"Rate limit exceeded",
                severity=ErrorSeverity.RECOVERABLE,
                original_exception=error
            )

        # ... other string-based detection ...
```

### Environment Variable Configuration

Add these environment variables to your deployment configuration:

**File: `.env` (for local development)**

```bash
# LLM Error Handling Feature Flags
USE_LITELLM_EXCEPTIONS=true
ENABLE_CIRCUIT_BREAKER=true
ENABLE_RETRY_LOGIC=true
ENABLE_ERROR_DB_LOGGING=true

# Circuit Breaker Configuration
CIRCUIT_BREAKER_FAILURE_THRESHOLD=5
CIRCUIT_BREAKER_TIMEOUT_SECONDS=300

# Retry Configuration
MAX_RETRY_ATTEMPTS=3
RETRY_BASE_DELAY_SECONDS=2.0
RETRY_MAX_DELAY_SECONDS=60.0
```

**For production deployment**, set these via your deployment system (systemd environment files, Docker env vars, etc.).

### Gradual Rollout Strategy

1. **Phase 1: Database Logging Only**
   ```bash
   USE_LITELLM_EXCEPTIONS=true
   ENABLE_CIRCUIT_BREAKER=false
   ENABLE_RETRY_LOGIC=false
   ENABLE_ERROR_DB_LOGGING=true
   ```
   - Monitor error logging works correctly
   - Verify no performance impact
   - Duration: 24 hours

2. **Phase 2: Add Retry Logic**
   ```bash
   ENABLE_RETRY_LOGIC=true
   ```
   - Monitor retry behavior
   - Check API cost impact
   - Verify no infinite retry loops
   - Duration: 48 hours

3. **Phase 3: Enable Circuit Breaker**
   ```bash
   ENABLE_CIRCUIT_BREAKER=true
   ```
   - Monitor circuit breaker triggers
   - Verify failover to alternate models works
   - Check no service disruption
   - Duration: 1 week

4. **Phase 4: Full Rollout**
   - All flags enabled
   - Monitor for 2 weeks
   - Collect metrics and optimize thresholds

### Quick Rollback Procedure

If issues are detected during rollout:

```bash
# Option 1: Disable specific feature
export ENABLE_CIRCUIT_BREAKER=false  # Disable just circuit breaker
systemctl restart aunoo-api

# Option 2: Revert to legacy behavior completely
export USE_LITELLM_EXCEPTIONS=false  # Disable all new error handling
systemctl restart aunoo-api

# Option 3: Disable all new features
export USE_LITELLM_EXCEPTIONS=false
export ENABLE_CIRCUIT_BREAKER=false
export ENABLE_RETRY_LOGIC=false
export ENABLE_ERROR_DB_LOGGING=false
systemctl restart aunoo-api
```

### Monitoring Feature Flag Usage

Log feature flags at application startup in `app/main.py`:

```python
from app.config import feature_flags
import logging

logger = logging.getLogger(__name__)

# At application startup
feature_flags.log_feature_flags(logger)
```

This ensures every deployment logs the active configuration, making debugging easier.

---

### Error Logging to Database (Once Methods Exist)

When the facade methods are implemented, use this pattern:

```python
# Log processing errors
db.facade.log_llm_processing_error({
    'article_id': article_id,
    'error_type': error.__class__.__name__,
    'error_message': str(error),
    'severity': severity.value,
    'model_name': self.model_name,
    'retry_count': retry_count,
    'will_retry': will_retry,
    'context': json.dumps({"additional": "data"}),
    'timestamp': datetime.utcnow().isoformat()
})
```

### Updating Article Status (Once Methods Exist)

Update article processing status through the facade:

```python
# Update article status on error
db.facade.update_article_llm_status({
    'article_id': article_id,
    'llm_status': 'error',
    'error_type': error.__class__.__name__,
    'error_message': str(error),
    'processing_metadata': json.dumps({
        "retry_count": retry_count,
        "will_retry": True,
        "timestamp": datetime.utcnow().isoformat()
    })
})

# Update status on skip
db.facade.update_article_llm_status({
    'article_id': article_id,
    'llm_status': 'skipped',
    'error_type': 'ContextWindowExceededError',
    'error_message': 'Content too large',
    'processing_metadata': json.dumps({
        "reason": "content_too_large",
        "max_tokens": max_context_window,
        "actual_tokens": estimated_tokens
    })
})
```

### Integration in Exception Handlers

Example integration in `app/ai_models.py` (once facade methods exist):

```python
from datetime import datetime
from app.database import get_database_instance

# In generate_response method
except AuthenticationError as e:
    logger.error(f"🚨 FATAL: Authentication failed for {self.model_name}: {e}")

    # Log fatal error to database (sync call - no await)
    if hasattr(self, 'current_article_id') and self.current_article_id:
        try:
            db = get_database_instance()
            db.facade.log_llm_processing_error({
                'article_id': self.current_article_id,
                'error_type': "AuthenticationError",
                'error_message': str(e),
                'severity': "fatal",
                'model_name': self.model_name,
                'retry_count': 0,
                'will_retry': False,
                'timestamp': datetime.utcnow().isoformat()
            })
        except Exception as db_error:
            logger.error(f"Failed to log error to database: {db_error}")

    raise PipelineError(
        f"Authentication failed - invalid API key for {self.model_name}",
        severity=ErrorSeverity.FATAL,
        original_exception=e
    )
```

### Batch Processing Error Tracking

In `app/services/automated_ingest_service.py`, track errors per article (once facade methods exist):

```python
import json

# Track error in batch processing
for article in articles:
    try:
        result = await self._process_single_article_async(article, topic)
    except PipelineError as e:
        # Log to database via facade (sync call within async function)
        try:
            db.facade.update_article_llm_status({
                'article_id': article.get('id'),
                'llm_status': "error" if e.severity != ErrorSeverity.FATAL else "failed",
                'error_type': e.original_exception.__class__.__name__ if e.original_exception else "PipelineError",
                'error_message': str(e),
                'processing_metadata': json.dumps({
                    "severity": e.severity.value,
                    "original_error": str(e.original_exception) if e.original_exception else None
                })
            })
        except Exception as db_error:
            logger.error(f"Failed to update article status in database: {db_error}")

        # Re-raise if fatal
        if e.severity == ErrorSeverity.FATAL:
            raise
```

**Note**: The database facade methods are synchronous, so they can be called directly from both sync and async contexts without await.

---

## WebSocket Error Notification Integration

Errors should be communicated to the frontend through the existing WebSocket status messaging system.

### WebSocket Manager Integration

**IMPORTANT**: The WebSocket manager is located in `app/routes/websocket_routes.py` and does **NOT** have a `broadcast()` method. Instead, it uses job-specific subscriptions.

```python
from app.routes.websocket_routes import manager as websocket_manager

# The manager has these methods:
# - send_job_update(job_id, data) - Send to all subscribers of a job
# - send_direct_message(connection_id, data) - Send to specific connection
```

### Sending Error Notifications

```python
async def notify_pipeline_error(job_id: str, error: PipelineError, context: dict = None):
    """
    Send pipeline error to connected clients via WebSocket

    Args:
        job_id: Job/batch ID that clients are subscribed to
        error: PipelineError instance
        context: Additional context (article_id, batch_id, etc.)
    """
    data = {
        "status": "error",
        "severity": error.severity.value,
        "message": str(error),
        "error_type": error.original_exception.__class__.__name__ if error.original_exception else "Unknown",
        "timestamp": datetime.utcnow().isoformat(),
        "context": context or {}
    }

    await websocket_manager.send_job_update(job_id, data)
```

### Integration in Batch Processing

In `app/services/automated_ingest_service.py`:

```python
# Fatal error notification
except PipelineError as e:
    if e.severity == ErrorSeverity.FATAL:
        logger.error(f"🚨 FATAL ERROR in batch - stopping: {e}")

        # Notify via WebSocket (if job_id available)
        if job_id:
            await notify_pipeline_error(
                job_id=job_id,
                error=e,
                context={
                    "batch_id": batch_id,
                    "articles_processed": processed_count,
                    "articles_total": total_count,
                    "stopped_at": article_uri
                }
            )

        raise

# Rate limit notification
except RateLimitError as e:
    logger.warning(f"⏸️ Rate limit hit - pausing batch: {e}")

    if job_id:
        await websocket_manager.send_job_update(job_id, {
            "status": "rate_limited",
            "message": "Rate limit reached. Processing will resume after delay.",
            "retry_after": delay_seconds,
            "timestamp": datetime.utcnow().isoformat()
        })
```

### Status Update Messages

```python
# Success notification
if job_id:
    await websocket_manager.send_job_update(job_id, {
        "status": "processing",
        "progress": {
            "current": current_count,
            "total": total_count,
            "percentage": (current_count / total_count) * 100
        }
    })

# Completion notification
if job_id:
    await websocket_manager.send_job_update(job_id, {
        "status": "completed",
        "stats": {
            "total": total_count,
            "succeeded": success_count,
            "failed": error_count,
            "skipped": skip_count,
            "rate_limited": rate_limit_count
        }
    })
```

**Note**: WebSocket notifications require a `job_id` that clients have subscribed to. Make sure the batch processing service generates and tracks job IDs for WebSocket integration.

---

## Job ID Tracking and Management

To enable WebSocket notifications and error tracking across the pipeline, we need a consistent job ID that's generated and passed through all processing stages.

### Job ID Generation

Add to `app/services/automated_ingest_service.py`:

```python
import uuid
from datetime import datetime

class AutomatedIngestService:
    """Service for automated article ingestion with job tracking"""

    def __init__(self, db):
        self.db = db
        self.current_jobs = {}  # Track active jobs: {job_id: job_metadata}

    def generate_job_id(self, prefix="ingest"):
        """
        Generate unique job ID with timestamp and UUID.

        Args:
            prefix: Job type prefix (e.g., "ingest", "analysis", "bulk")

        Returns:
            str: Unique job ID like "ingest_20250118_a1b2c3d4"
        """
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        unique_id = str(uuid.uuid4())[:8]
        return f"{prefix}_{timestamp}_{unique_id}"

    def register_job(self, job_id, metadata=None):
        """
        Register a job for tracking.

        Args:
            job_id: Unique job identifier
            metadata: Optional dict with job metadata (topic, keyword_group, etc.)
        """
        self.current_jobs[job_id] = {
            'job_id': job_id,
            'started_at': datetime.utcnow(),
            'status': 'running',
            'metadata': metadata or {}
        }
        logger.info(f"Registered job {job_id} with metadata: {metadata}")

    def update_job_status(self, job_id, status, **kwargs):
        """
        Update job status and metadata.

        Args:
            job_id: Job identifier
            status: New status ('running', 'completed', 'error', 'partial')
            **kwargs: Additional fields to update
        """
        if job_id in self.current_jobs:
            self.current_jobs[job_id]['status'] = status
            self.current_jobs[job_id].update(kwargs)
            logger.info(f"Updated job {job_id} status to {status}")

    def complete_job(self, job_id, results=None):
        """
        Mark job as completed and optionally remove from tracking.

        Args:
            job_id: Job identifier
            results: Optional results dict
        """
        if job_id in self.current_jobs:
            self.current_jobs[job_id]['status'] = 'completed'
            self.current_jobs[job_id]['completed_at'] = datetime.utcnow()
            if results:
                self.current_jobs[job_id]['results'] = results

            logger.info(f"Completed job {job_id}")

            # Keep completed jobs for 1 hour for status queries
            # In production, you might store these in database or cache
```

### Integration in Batch Processing

Update `app/services/automated_ingest_service.py` to use job IDs:

```python
async def process_articles_batch(self, articles, topic, keywords, job_id=None):
    """
    Process batch of articles with job tracking.

    Args:
        articles: List of article dicts
        topic: Topic string
        keywords: List of keyword strings
        job_id: Optional job ID (will be generated if not provided)

    Returns:
        dict: Processing results with job_id
    """
    # Generate or use provided job_id
    if not job_id:
        job_id = self.generate_job_id(prefix="batch_ingest")

    # Register job
    self.register_job(job_id, metadata={
        'topic': topic,
        'keywords': keywords,
        'article_count': len(articles),
        'batch_type': 'automated_ingest'
    })

    # Initialize results
    results = {
        'job_id': job_id,
        'started_at': datetime.utcnow().isoformat(),
        'processed': 0,
        'saved': 0,
        'skipped': 0,
        'errors': [],
        'rate_limited': 0
    }

    try:
        # Send initial WebSocket notification
        from app.routes.websocket_routes import manager as websocket_manager

        await websocket_manager.send_job_update(job_id, {
            'status': 'started',
            'message': f'Processing {len(articles)} articles for topic: {topic}',
            'total': len(articles),
            'timestamp': datetime.utcnow().isoformat()
        })

        # Process articles
        for idx, article in enumerate(articles):
            try:
                # Add job_id to article processing context
                article['_job_id'] = job_id
                article['_batch_index'] = idx

                # Process single article (will use job_id for error notifications)
                result = await self._process_single_article_async(
                    article, topic, job_id=job_id
                )

                results['processed'] += 1

                # Send progress update
                await websocket_manager.send_job_update(job_id, {
                    'status': 'processing',
                    'progress': {
                        'current': idx + 1,
                        'total': len(articles),
                        'percentage': ((idx + 1) / len(articles)) * 100
                    },
                    'timestamp': datetime.utcnow().isoformat()
                })

            except PipelineError as e:
                if e.severity == ErrorSeverity.FATAL:
                    # Fatal error - stop processing
                    logger.error(f"🚨 FATAL ERROR in job {job_id}: {e}")

                    # Notify via WebSocket
                    await websocket_manager.send_job_update(job_id, {
                        'status': 'error',
                        'severity': 'fatal',
                        'message': str(e),
                        'error_type': e.original_exception.__class__.__name__ if e.original_exception else 'Unknown',
                        'stopped_at_index': idx,
                        'timestamp': datetime.utcnow().isoformat()
                    })

                    # Update job status
                    self.update_job_status(job_id, 'error', error=str(e))

                    # Re-raise to stop processing
                    raise

                else:
                    # Non-fatal error - log and continue
                    results['errors'].append({
                        'article_index': idx,
                        'article_uri': article.get('uri'),
                        'error': str(e),
                        'severity': e.severity.value
                    })

            except Exception as e:
                logger.error(f"Unexpected error processing article {idx}: {e}")
                results['errors'].append({
                    'article_index': idx,
                    'article_uri': article.get('uri'),
                    'error': str(e)
                })

        # Mark job as completed
        results['completed_at'] = datetime.utcnow().isoformat()
        self.complete_job(job_id, results=results)

        # Send completion notification
        await websocket_manager.send_job_update(job_id, {
            'status': 'completed',
            'results': {
                'total': len(articles),
                'processed': results['processed'],
                'saved': results['saved'],
                'skipped': results['skipped'],
                'errors': len(results['errors']),
                'rate_limited': results['rate_limited']
            },
            'timestamp': datetime.utcnow().isoformat()
        })

        return results

    except Exception as e:
        # Unhandled exception - mark job as error
        logger.exception(f"Job {job_id} failed with unhandled exception")
        self.update_job_status(job_id, 'error', error=str(e))

        # Send error notification
        await websocket_manager.send_job_update(job_id, {
            'status': 'error',
            'message': f'Job failed: {str(e)}',
            'timestamp': datetime.utcnow().isoformat()
        })

        raise


async def _process_single_article_async(self, article, topic, job_id=None):
    """
    Process single article with job tracking.

    Args:
        article: Article dict
        topic: Topic string
        job_id: Job ID for WebSocket notifications (optional)

    Returns:
        dict: Processing result
    """
    article_uri = article.get('uri', 'unknown')

    # Extract job_id from article context if not provided
    if not job_id and '_job_id' in article:
        job_id = article['_job_id']

    try:
        # ... existing article processing logic ...

        # On error, include job_id in error logging
        pass

    except PipelineError as e:
        # Log error with job context
        if job_id:
            logger.error(f"[Job {job_id}] Article {article_uri} error: {e}")

            # Send article-level error notification
            from app.routes.websocket_routes import manager as websocket_manager
            await websocket_manager.send_job_update(job_id, {
                'type': 'article_error',
                'article_uri': article_uri,
                'error': str(e),
                'severity': e.severity.value,
                'timestamp': datetime.utcnow().isoformat()
            })

        # Re-raise for batch handler
        raise
```

### Job ID in Error Logging

When logging errors to the database, include job_id for traceability:

```python
# In exception handlers
db.facade.log_llm_processing_error({
    'article_id': article_id,
    'error_type': error.__class__.__name__,
    'error_message': str(error),
    'severity': severity.value,
    'model_name': self.model_name,
    'retry_count': retry_count,
    'will_retry': will_retry,
    'context': json.dumps({
        'job_id': job_id,  # Include job_id in context
        'article_uri': article_uri,
        'batch_index': article.get('_batch_index'),
        'timestamp': datetime.utcnow().isoformat()
    }),
    'timestamp': datetime.utcnow().isoformat()
})
```

### API Endpoint Updates

Update API endpoints to return job_id:

```python
@app.post("/api/ingest/batch")
async def ingest_batch(request: Request):
    """Start batch ingestion with job tracking"""

    # Parse request
    data = await request.json()
    articles = data.get('articles', [])
    topic = data.get('topic')
    keywords = data.get('keywords', [])

    # Generate job_id
    job_id = automated_ingest_service.generate_job_id(prefix="api_ingest")

    # Start processing in background
    asyncio.create_task(
        automated_ingest_service.process_articles_batch(
            articles, topic, keywords, job_id=job_id
        )
    )

    # Return job_id immediately for client to subscribe
    return {
        'status': 'started',
        'job_id': job_id,
        'message': f'Processing {len(articles)} articles',
        'websocket_subscribe': f'/ws/jobs/{job_id}'
    }
```

### Database Schema for Job Tracking (Optional)

For persistent job tracking, add a jobs table:

```sql
CREATE TABLE processing_jobs (
    id SERIAL PRIMARY KEY,
    job_id VARCHAR(255) NOT NULL UNIQUE,
    job_type VARCHAR(50) NOT NULL,  -- 'batch_ingest', 'analysis', etc.
    status VARCHAR(50) NOT NULL,     -- 'running', 'completed', 'error'
    started_at TIMESTAMP NOT NULL,
    completed_at TIMESTAMP,
    metadata JSONB,
    results JSONB,
    error_message TEXT
);

CREATE INDEX idx_processing_jobs_job_id ON processing_jobs(job_id);
CREATE INDEX idx_processing_jobs_status ON processing_jobs(status);
CREATE INDEX idx_processing_jobs_started_at ON processing_jobs(started_at);
```

This enables job history queries and persistent tracking across service restarts.

---

## Retry State Persistence

To enable retry state to survive service restarts and implement circuit breaker patterns, we need persistent storage of retry/failure state.

### Database Schema Additions

Add new tables for tracking LLM errors, retry state, and job processing:

```sql
-- Table for logging LLM processing errors
CREATE TABLE llm_processing_errors (
    id SERIAL PRIMARY KEY,
    article_id INTEGER,  -- Optional reference to articles table
    error_type VARCHAR(255) NOT NULL,
    error_message TEXT NOT NULL,
    severity VARCHAR(50) NOT NULL,  -- 'fatal', 'recoverable', 'skippable', 'degraded'
    model_name VARCHAR(255) NOT NULL,
    retry_count INTEGER DEFAULT 0,
    will_retry BOOLEAN DEFAULT FALSE,
    context JSONB,  -- Additional context (job_id, article_uri, etc.)
    timestamp TIMESTAMP NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    INDEX idx_error_type (error_type),
    INDEX idx_severity (severity),
    INDEX idx_model_name (model_name),
    INDEX idx_timestamp (timestamp),
    INDEX idx_article_id (article_id)
);

-- Table for tracking LLM retry state (circuit breaker)
CREATE TABLE llm_retry_state (
    id SERIAL PRIMARY KEY,
    model_name VARCHAR(255) NOT NULL UNIQUE,
    consecutive_failures INTEGER DEFAULT 0,
    last_failure_time TIMESTAMP,
    last_success_time TIMESTAMP,
    circuit_state VARCHAR(50) DEFAULT 'closed',  -- 'closed', 'open', 'half_open'
    circuit_opened_at TIMESTAMP,
    failure_rate FLOAT DEFAULT 0.0,
    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    metadata JSONB,

    INDEX idx_model_name (model_name),
    INDEX idx_circuit_state (circuit_state)
);

-- Add LLM status tracking columns to articles table
ALTER TABLE articles ADD COLUMN IF NOT EXISTS llm_status VARCHAR(50);
ALTER TABLE articles ADD COLUMN IF NOT EXISTS llm_status_updated_at TIMESTAMP;
ALTER TABLE articles ADD COLUMN IF NOT EXISTS llm_error_type VARCHAR(255);
ALTER TABLE articles ADD COLUMN IF NOT EXISTS llm_error_message TEXT;
ALTER TABLE articles ADD COLUMN IF NOT EXISTS llm_processing_metadata JSONB;

CREATE INDEX IF NOT EXISTS idx_articles_llm_status ON articles(llm_status);

-- Optional: Table for tracking processing jobs
CREATE TABLE processing_jobs (
    id SERIAL PRIMARY KEY,
    job_id VARCHAR(255) NOT NULL UNIQUE,
    job_type VARCHAR(50) NOT NULL,  -- 'batch_ingest', 'analysis', 'bulk_research'
    status VARCHAR(50) NOT NULL,     -- 'running', 'completed', 'error', 'partial'
    started_at TIMESTAMP NOT NULL,
    completed_at TIMESTAMP,
    metadata JSONB,  -- topic, keywords, article_count, etc.
    results JSONB,   -- processed count, errors, etc.
    error_message TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_processing_jobs_job_id ON processing_jobs(job_id);
CREATE INDEX idx_processing_jobs_job_type ON processing_jobs(job_type);
CREATE INDEX idx_processing_jobs_status ON processing_jobs(status);
CREATE INDEX idx_processing_jobs_started_at ON processing_jobs(started_at);
```

### Database Migration

Create an Alembic migration for these changes:

```bash
# Generate migration
alembic revision -m "add_llm_error_handling_tables"
```

```python
"""add_llm_error_handling_tables

Revision ID: xxxxx
Revises: previous_revision
Create Date: 2025-01-18

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers
revision = 'xxxxx'
down_revision = 'previous_revision'
branch_labels = None
depends_on = None


def upgrade():
    # Create llm_processing_errors table
    op.create_table(
        'llm_processing_errors',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('article_id', sa.Integer(), nullable=True),
        sa.Column('error_type', sa.String(255), nullable=False),
        sa.Column('error_message', sa.Text(), nullable=False),
        sa.Column('severity', sa.String(50), nullable=False),
        sa.Column('model_name', sa.String(255), nullable=False),
        sa.Column('retry_count', sa.Integer(), server_default='0'),
        sa.Column('will_retry', sa.Boolean(), server_default='false'),
        sa.Column('context', postgresql.JSONB(), nullable=True),
        sa.Column('timestamp', sa.TIMESTAMP(), nullable=False),
        sa.Column('created_at', sa.TIMESTAMP(), server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_llm_errors_error_type', 'llm_processing_errors', ['error_type'])
    op.create_index('idx_llm_errors_severity', 'llm_processing_errors', ['severity'])
    op.create_index('idx_llm_errors_model_name', 'llm_processing_errors', ['model_name'])
    op.create_index('idx_llm_errors_timestamp', 'llm_processing_errors', ['timestamp'])
    op.create_index('idx_llm_errors_article_id', 'llm_processing_errors', ['article_id'])

    # Create llm_retry_state table
    op.create_table(
        'llm_retry_state',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('model_name', sa.String(255), nullable=False),
        sa.Column('consecutive_failures', sa.Integer(), server_default='0'),
        sa.Column('last_failure_time', sa.TIMESTAMP(), nullable=True),
        sa.Column('last_success_time', sa.TIMESTAMP(), nullable=True),
        sa.Column('circuit_state', sa.String(50), server_default='closed'),
        sa.Column('circuit_opened_at', sa.TIMESTAMP(), nullable=True),
        sa.Column('failure_rate', sa.Float(), server_default='0.0'),
        sa.Column('last_updated', sa.TIMESTAMP(), server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('metadata', postgresql.JSONB(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('model_name')
    )
    op.create_index('idx_llm_retry_model_name', 'llm_retry_state', ['model_name'])
    op.create_index('idx_llm_retry_circuit_state', 'llm_retry_state', ['circuit_state'])

    # Add columns to articles table
    op.add_column('articles', sa.Column('llm_status', sa.String(50), nullable=True))
    op.add_column('articles', sa.Column('llm_status_updated_at', sa.TIMESTAMP(), nullable=True))
    op.add_column('articles', sa.Column('llm_error_type', sa.String(255), nullable=True))
    op.add_column('articles', sa.Column('llm_error_message', sa.Text(), nullable=True))
    op.add_column('articles', sa.Column('llm_processing_metadata', postgresql.JSONB(), nullable=True))
    op.create_index('idx_articles_llm_status', 'articles', ['llm_status'])

    # Optional: Create processing_jobs table
    op.create_table(
        'processing_jobs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('job_id', sa.String(255), nullable=False),
        sa.Column('job_type', sa.String(50), nullable=False),
        sa.Column('status', sa.String(50), nullable=False),
        sa.Column('started_at', sa.TIMESTAMP(), nullable=False),
        sa.Column('completed_at', sa.TIMESTAMP(), nullable=True),
        sa.Column('metadata', postgresql.JSONB(), nullable=True),
        sa.Column('results', postgresql.JSONB(), nullable=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('created_at', sa.TIMESTAMP(), server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('job_id')
    )
    op.create_index('idx_jobs_job_id', 'processing_jobs', ['job_id'])
    op.create_index('idx_jobs_job_type', 'processing_jobs', ['job_type'])
    op.create_index('idx_jobs_status', 'processing_jobs', ['status'])
    op.create_index('idx_jobs_started_at', 'processing_jobs', ['started_at'])


def downgrade():
    # Drop processing_jobs table
    op.drop_index('idx_jobs_started_at', table_name='processing_jobs')
    op.drop_index('idx_jobs_status', table_name='processing_jobs')
    op.drop_index('idx_jobs_job_type', table_name='processing_jobs')
    op.drop_index('idx_jobs_job_id', table_name='processing_jobs')
    op.drop_table('processing_jobs')

    # Remove columns from articles table
    op.drop_index('idx_articles_llm_status', table_name='articles')
    op.drop_column('articles', 'llm_processing_metadata')
    op.drop_column('articles', 'llm_error_message')
    op.drop_column('articles', 'llm_error_type')
    op.drop_column('articles', 'llm_status_updated_at')
    op.drop_column('articles', 'llm_status')

    # Drop llm_retry_state table
    op.drop_index('idx_llm_retry_circuit_state', table_name='llm_retry_state')
    op.drop_index('idx_llm_retry_model_name', table_name='llm_retry_state')
    op.drop_table('llm_retry_state')

    # Drop llm_processing_errors table
    op.drop_index('idx_llm_errors_article_id', table_name='llm_processing_errors')
    op.drop_index('idx_llm_errors_timestamp', table_name='llm_processing_errors')
    op.drop_index('idx_llm_errors_model_name', table_name='llm_processing_errors')
    op.drop_index('idx_llm_errors_severity', table_name='llm_processing_errors')
    op.drop_index('idx_llm_errors_error_type', table_name='llm_processing_errors')
    op.drop_table('llm_processing_errors')
```

### Database Facade Methods

Add to `DatabaseQueryFacade`:

```python
def get_llm_retry_state(self, model_name):
    """Get current retry/failure state for a model"""
    return self._execute_with_rollback(
        select(llm_retry_state).where(
            llm_retry_state.c.model_name == model_name
        )
    ).mappings().fetchone()

def update_llm_retry_state(self, params):
    """
    Update retry/failure state for a model

    Args:
        params: dict with keys:
            - model_name: str
            - consecutive_failures: int
            - last_failure_time: datetime (optional)
            - last_success_time: datetime (optional)
            - circuit_state: str ('closed', 'open', 'half_open')
            - circuit_opened_at: datetime (optional)
            - failure_rate: float
            - metadata: dict (optional)
    """
    # Upsert pattern
    existing = self.get_llm_retry_state(params['model_name'])

    if existing:
        self._execute_with_rollback(
            update(llm_retry_state).where(
                llm_retry_state.c.model_name == params['model_name']
            ).values(**params)
        )
    else:
        self._execute_with_rollback(
            insert(llm_retry_state).values(**params)
        )

def reset_llm_retry_state(self, model_name):
    """Reset retry state for a model (after successful recovery)"""
    self._execute_with_rollback(
        update(llm_retry_state).where(
            llm_retry_state.c.model_name == model_name
        ).values(
            consecutive_failures=0,
            last_success_time=datetime.utcnow(),
            circuit_state='closed',
            circuit_opened_at=None,
            failure_rate=0.0,
            last_updated=datetime.utcnow()
        )
    )
```

### Integration with Retry Logic

Update `app/ai_models.py` to track retry state:

```python
def _record_failure(self, error: Exception):
    """Record failure in persistent state"""
    try:
        db = get_database_instance()
        state = db.facade.get_llm_retry_state(self.model_name)

        consecutive_failures = (state['consecutive_failures'] + 1) if state else 1

        db.facade.update_llm_retry_state({
            'model_name': self.model_name,
            'consecutive_failures': consecutive_failures,
            'last_failure_time': datetime.utcnow(),
            'failure_rate': self._calculate_failure_rate(consecutive_failures),
            'metadata': json.dumps({
                'last_error_type': error.__class__.__name__,
                'last_error_message': str(error)
            })
        })
    except Exception as e:
        logger.error(f"Failed to record failure state: {e}")

def _record_success(self):
    """Record success in persistent state"""
    try:
        db = get_database_instance()
        db.facade.reset_llm_retry_state(self.model_name)
    except Exception as e:
        logger.error(f"Failed to record success state: {e}")

def _calculate_failure_rate(self, consecutive_failures):
    """Calculate exponential failure rate"""
    # Simple exponential: 0.5^(consecutive_failures)
    return min(1.0, consecutive_failures / 10.0)
```

---

## Circuit Breaker Pattern

Implement circuit breaker pattern to prevent cascading failures and reduce API costs during outages.

### Circuit Breaker States

1. **CLOSED** (normal): All requests pass through
2. **OPEN** (failure): All requests fail fast without calling API
3. **HALF_OPEN** (testing): Limited requests allowed to test recovery

### Implementation

Create `app/utils/circuit_breaker.py`:

```python
"""
Circuit Breaker pattern for LLM API calls
"""
from datetime import datetime, timedelta
from typing import Optional
import logging
from app.database import get_database_instance
from app.exceptions import PipelineError, ErrorSeverity

logger = logging.getLogger(__name__)


class CircuitBreakerOpen(Exception):
    """Raised when circuit breaker is open"""
    pass


class CircuitBreaker:
    """
    Circuit breaker for LLM API calls with persistent state
    """

    # Configuration
    FAILURE_THRESHOLD = 5  # Open circuit after N consecutive failures
    TIMEOUT_DURATION = 300  # Keep circuit open for 5 minutes
    HALF_OPEN_MAX_ATTEMPTS = 3  # Allow N attempts in half-open state

    def __init__(self, model_name: str):
        self.model_name = model_name
        self.db = get_database_instance()

    def get_state(self) -> dict:
        """Get current circuit state from database"""
        state = self.db.facade.get_llm_retry_state(self.model_name)

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
        Check if circuit allows request

        Returns:
            True if request should proceed

        Raises:
            CircuitBreakerOpen if circuit is open and timeout hasn't expired
        """
        state = self.get_state()
        circuit_state = state['circuit_state']
        consecutive_failures = state['consecutive_failures']
        circuit_opened_at = state.get('circuit_opened_at')

        # CLOSED state - allow all requests
        if circuit_state == 'closed':
            if consecutive_failures >= self.FAILURE_THRESHOLD:
                # Threshold exceeded - open circuit
                self._open_circuit()
                raise CircuitBreakerOpen(
                    f"Circuit breaker opened for {self.model_name} after "
                    f"{consecutive_failures} consecutive failures"
                )
            return True

        # OPEN state - check if timeout has elapsed
        if circuit_state == 'open':
            if circuit_opened_at:
                opened_time = circuit_opened_at
                if isinstance(opened_time, str):
                    opened_time = datetime.fromisoformat(opened_time)

                elapsed = datetime.utcnow() - opened_time

                if elapsed.total_seconds() >= self.TIMEOUT_DURATION:
                    # Timeout elapsed - enter half-open state
                    self._half_open_circuit()
                    return True

            # Circuit still open
            raise CircuitBreakerOpen(
                f"Circuit breaker is open for {self.model_name}. "
                f"Will retry after timeout."
            )

        # HALF_OPEN state - allow limited requests
        if circuit_state == 'half_open':
            return True

        return False

    def record_success(self):
        """Record successful request - close circuit"""
        logger.info(f"Circuit breaker: Success for {self.model_name} - closing circuit")
        self.db.facade.reset_llm_retry_state(self.model_name)

    def record_failure(self, error: Exception):
        """Record failed request - may open circuit"""
        state = self.get_state()
        consecutive_failures = state['consecutive_failures'] + 1

        logger.warning(
            f"Circuit breaker: Failure {consecutive_failures} for {self.model_name}"
        )

        self.db.facade.update_llm_retry_state({
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
        """Open the circuit breaker"""
        logger.error(f"🔴 Circuit breaker OPENED for {self.model_name}")

        self.db.facade.update_llm_retry_state({
            'model_name': self.model_name,
            'circuit_state': 'open',
            'circuit_opened_at': datetime.utcnow()
        })

    def _half_open_circuit(self):
        """Enter half-open state to test recovery"""
        logger.info(f"🟡 Circuit breaker HALF-OPEN for {self.model_name}")

        self.db.facade.update_llm_retry_state({
            'model_name': self.model_name,
            'circuit_state': 'half_open'
        })

    def _close_circuit(self):
        """Close the circuit breaker (normal operation)"""
        logger.info(f"🟢 Circuit breaker CLOSED for {self.model_name}")
        self.db.facade.reset_llm_retry_state(self.model_name)
```

### Integration with LiteLLMModel

Update `app/ai_models.py`:

```python
from app.utils.circuit_breaker import CircuitBreaker, CircuitBreakerOpen

class LiteLLMModel:
    def __init__(self, model_name, ...):
        # ... existing init code ...
        self.circuit_breaker = CircuitBreaker(model_name)

    def generate_response(self, messages, ...):
        # Check circuit breaker before making API call
        try:
            self.circuit_breaker.check_circuit()
        except CircuitBreakerOpen as e:
            logger.error(f"🔴 Circuit breaker open: {e}")
            # Try fallback immediately instead of calling failed API
            return self._try_fallback_model(
                messages, _attempted_models,
                f"Circuit breaker open: {str(e)}"
            )

        try:
            response = self.router.completion(...)

            # Record success in circuit breaker
            self.circuit_breaker.record_success()

            return response.choices[0].message.content

        except AuthenticationError as e:
            # Fatal error - don't trigger circuit breaker
            # (auth errors are permanent, not transient)
            raise PipelineError(...)

        except (RateLimitError, Timeout, APIConnectionError) as e:
            # Transient error - record in circuit breaker
            self.circuit_breaker.record_failure(e)

            # ... retry logic ...

        except Exception as e:
            # Unknown error - record in circuit breaker
            self.circuit_breaker.record_failure(e)
            raise
```

### Benefits of Circuit Breaker

1. **Fail Fast**: Stop calling failing APIs immediately instead of wasting time/money
2. **Automatic Recovery**: Automatically tests recovery after timeout
3. **Cost Reduction**: Prevents expensive API calls during outages
4. **Graceful Degradation**: Falls back to alternative models immediately
5. **Persistent State**: Survives service restarts (state in database)

---

## Performance Impact Analysis

### Expected Performance Impact

#### Retry Delays
- **Rate Limit Retries**: 2-60 seconds per retry attempt
  - Attempt 1: ~2 seconds delay
  - Attempt 2: ~4 seconds delay
  - Attempt 3: ~8 seconds delay
  - Total: Up to 14 seconds additional latency per rate-limited request

- **Network Error Retries**: 1-10 seconds per retry
  - Attempt 1: ~1 second delay
  - Attempt 2: ~2 seconds delay
  - Total: Up to 3 seconds additional latency per network error

#### Throughput Impact
- **Baseline**: ~X articles/minute (no errors)
- **With Retries**: 10-20% reduction in throughput during error conditions
- **Worst Case**: 50% reduction if frequent rate limiting occurs

### Mitigation Strategies

1. **Parallel Processing During Waits**
   ```python
   # Process multiple articles concurrently
   # While one article is in retry delay, others can process
   tasks = [
       self._process_single_article_async(article, topic)
       for article in batch
   ]
   results = await asyncio.gather(*tasks, return_exceptions=True)
   ```

2. **Adaptive Batch Sizing**
   ```python
   # Reduce batch size when rate limits detected
   if rate_limit_count > threshold:
       batch_size = max(batch_size // 2, min_batch_size)
       logger.info(f"Reducing batch size to {batch_size} due to rate limits")
   ```

3. **Request Queuing**
   ```python
   # Queue requests to respect rate limits proactively
   from app.utils.rate_limiter import TokenBucketRateLimiter

   rate_limiter = TokenBucketRateLimiter(
       requests_per_minute=model_rate_limit
   )

   await rate_limiter.acquire()
   result = await self.ai_model.generate_response(messages)
   ```

### Cost Impact

#### API Call Costs
- **Retry Overhead**: Each retry = 1 additional API call
- **Expected**: 5-10% increase in API calls due to transient errors
- **Fallback Models**: May reduce costs if fallback is cheaper model

#### Monitoring Recommendations
```python
# Track retry costs
class RetryMetrics:
    def __init__(self):
        self.retry_counts = defaultdict(int)
        self.fallback_counts = defaultdict(int)
        self.total_cost = 0.0

    def record_retry(self, model: str, cost: float):
        self.retry_counts[model] += 1
        self.total_cost += cost
        logger.info(f"Retry cost: ${cost:.4f} for {model}")
```

### Performance Benchmarks

| Scenario | Baseline Time | With Retries | Impact |
|----------|--------------|--------------|--------|
| 100 articles, no errors | 5 min | 5 min | 0% |
| 100 articles, 5% rate limits | 5 min | 5.5-6 min | 10-20% |
| 100 articles, 10% errors | 5 min | 6-7 min | 20-40% |
| Auth failure (fatal) | 5 min | <10 sec | -98% (stops early) |

---

## Async/Sync Pattern Guidance

This implementation uses both async and sync patterns. Here's when to use each:

### When to Use Async

1. **Web Request Handlers**
   ```python
   @app.post("/api/process-articles")
   async def process_articles_endpoint(request: Request):
       # Use async for HTTP endpoints
       results = await automated_ingest_service.process_batch(articles)
       return results
   ```

2. **Batch Processing Operations**
   ```python
   async def process_articles_batch(self, articles: List[dict]):
       # Use async for concurrent processing
       tasks = [self._process_single_article_async(a) for a in articles]
       results = await asyncio.gather(*tasks, return_exceptions=True)
       return results
   ```

3. **Database Operations with Async Support**
   ```python
   # Use async for database facade methods
   await db.facade.update_article_status(article_id, status)
   await db.facade.log_processing_error(article_id, error)
   ```

4. **Retry Logic**
   ```python
   # Retry functions should be async
   result = await retry_with_backoff(
       async_function,
       retryable_exceptions=(RateLimitError,),
       config=retry_config
   )
   ```

### When to Use Sync

1. **LiteLLM Calls (if not async-native)**
   ```python
   # LiteLLM completion calls are typically sync
   response = self.router.completion(
       model=self.model_name,
       messages=messages
   )

   # Wrap in async context if needed
   async def generate_async(self, messages):
       loop = asyncio.get_event_loop()
       return await loop.run_in_executor(
           None,
           self._generate_sync,
           messages
       )
   ```

2. **File I/O Operations**
   ```python
   # Use sync for simple file operations
   with open(file_path, 'r') as f:
       content = f.read()

   # Or wrap in executor for async context
   loop = asyncio.get_event_loop()
   content = await loop.run_in_executor(None, read_file, file_path)
   ```

3. **CPU-Bound Operations**
   ```python
   # Heavy processing should use executor
   loop = asyncio.get_event_loop()
   result = await loop.run_in_executor(
       process_pool_executor,
       heavy_computation,
       data
   )
   ```

### Mixed Patterns in Exception Handling

```python
# Example: Sync LLM call with async retry logic
class LiteLLMModel:
    def generate_response(self, messages):
        """Sync method for backwards compatibility"""
        try:
            # Sync LLM call
            response = self.router.completion(...)
            return response.choices[0].message.content

        except RateLimitError as e:
            # Use async retry logic
            loop = asyncio.get_event_loop()
            return loop.run_until_complete(
                self._retry_with_backoff_async(messages)
            )

    async def _retry_with_backoff_async(self, messages):
        """Async retry helper"""
        config = RetryConfig(max_attempts=3)
        return await retry_with_backoff(
            self._generate_with_retry,
            messages,
            retryable_exceptions=(RateLimitError,),
            config=config
        )
```

### Best Practices

1. **Consistent Patterns**: Prefer fully async pipelines when possible
2. **Executor Usage**: Use `run_in_executor` to wrap sync calls in async context
3. **Avoid Blocking**: Never use `time.sleep()` in async code - use `await asyncio.sleep()`
4. **Error Handling**: Both sync and async should use the same exception types
5. **Testing**: Test both sync and async code paths

---

## Testing Strategy

### 1. Unit Tests

Create `tests/test_llm_exceptions.py`:

```python
"""
Unit tests for LLM exception handling
"""
import pytest
import asyncio
from unittest.mock import Mock, patch
import litellm
from app.ai_models import LiteLLMModel
from app.exceptions import PipelineError, ErrorSeverity
from app.relevance import RelevanceCalculator
from app.analyzers.article_analyzer import ArticleAnalyzer


class TestLLMExceptionHandling:
    """Test LiteLLM-specific exception handling"""

    @patch('litellm.Router.completion')
    def test_authentication_error_raises_fatal(self, mock_completion):
        """AuthenticationError should raise PipelineError with FATAL severity"""
        mock_completion.side_effect = litellm.AuthenticationError("Invalid API key")

        model = LiteLLMModel("gpt-4o-mini")

        with pytest.raises(PipelineError) as exc_info:
            model.generate_response([{"role": "user", "content": "test"}])

        assert exc_info.value.severity == ErrorSeverity.FATAL
        assert "Authentication failed" in str(exc_info.value)

    @patch('litellm.Router.completion')
    def test_rate_limit_triggers_retry(self, mock_completion):
        """RateLimitError should trigger retry logic"""
        # Fail twice, then succeed
        mock_completion.side_effect = [
            litellm.RateLimitError("Rate limit"),
            litellm.RateLimitError("Rate limit"),
            Mock(choices=[Mock(message=Mock(content="success"))])
        ]

        model = LiteLLMModel("gpt-4o-mini")
        result = model.generate_response([{"role": "user", "content": "test"}])

        assert result == "success"
        assert mock_completion.call_count == 3

    @patch('litellm.Router.completion')
    def test_context_window_returns_error_message(self, mock_completion):
        """ContextWindowExceededError should return error message, not crash"""
        mock_completion.side_effect = litellm.ContextWindowExceededError(
            "Maximum context length exceeded"
        )

        model = LiteLLMModel("gpt-4o-mini")
        result = model.generate_response([{"role": "user", "content": "test"}])

        assert isinstance(result, str)
        assert "Error:" in result
        assert "exceeds maximum length" in result.lower()

    def test_relevance_calculator_context_window(self):
        """RelevanceCalculator should return default scores on ContextWindowExceededError"""
        calc = RelevanceCalculator("gpt-4o-mini")

        with patch.object(calc.ai_model, 'generate_response') as mock_gen:
            mock_gen.side_effect = litellm.ContextWindowExceededError("Too large")

            result = calc.analyze_relevance(
                title="Test",
                source="Test Source",
                content="x" * 100000,  # Very large content
                topic="Test Topic",
                keywords="test"
            )

            assert result["topic_alignment_score"] == 0.0
            assert result["keyword_relevance_score"] == 0.0
            assert "exceeds maximum length" in result["overall_match_explanation"].lower()

    def test_article_analyzer_handles_rate_limit(self):
        """ArticleAnalyzer should convert RateLimitError to ArticleAnalyzerError"""
        from app.ai_models import get_ai_model

        ai_model = get_ai_model("gpt-4o-mini")
        analyzer = ArticleAnalyzer(ai_model)

        with patch.object(ai_model, 'generate_response') as mock_gen:
            mock_gen.side_effect = litellm.RateLimitError("Rate limit exceeded")

            from app.analyzers.article_analyzer import ArticleAnalyzerError

            with pytest.raises(ArticleAnalyzerError) as exc_info:
                analyzer.extract_title("Test article content")

            assert "Rate limit" in str(exc_info.value)


class TestBailOutBehavior:
    """Test bail-out behavior on fatal errors"""

    @pytest.mark.asyncio
    async def test_batch_stops_on_authentication_error(self):
        """Batch processing should stop on AuthenticationError"""
        from app.services.automated_ingest_service import AutomatedIngestService
        from app.database import get_database_instance

        db = get_database_instance()
        service = AutomatedIngestService(db)

        articles = [
            {"uri": f"http://test{i}.com", "title": f"Test {i}", "topic": "test"}
            for i in range(5)
        ]

        # Mock LLM to fail with AuthenticationError on second article
        with patch.object(service, '_analyze_article_content_async') as mock_analyze:
            async def side_effect(article, topic):
                if article["uri"] == "http://test1.com":
                    raise PipelineError(
                        "Auth failed",
                        severity=ErrorSeverity.FATAL,
                        original_exception=litellm.AuthenticationError("Invalid key")
                    )
                return article

            mock_analyze.side_effect = side_effect

            with pytest.raises(PipelineError) as exc_info:
                await service.process_articles_batch(articles, topic="test", keywords=[])

            assert exc_info.value.severity == ErrorSeverity.FATAL

    @pytest.mark.asyncio
    async def test_batch_continues_on_context_window_error(self):
        """Batch should continue processing when article is too large"""
        from app.services.automated_ingest_service import AutomatedIngestService
        from app.database import get_database_instance

        db = get_database_instance()
        service = AutomatedIngestService(db)

        articles = [
            {"uri": f"http://test{i}.com", "title": f"Test {i}", "topic": "test"}
            for i in range(3)
        ]

        # Mock LLM to fail with ContextWindowExceededError on middle article
        with patch.object(service, '_analyze_article_content_async') as mock_analyze:
            async def side_effect(article, topic):
                if article["uri"] == "http://test1.com":
                    raise litellm.ContextWindowExceededError("Too large")
                return article

            mock_analyze.side_effect = side_effect

            result = await service.process_articles_batch(articles, topic="test", keywords=[])

            # Should have processed 3 articles (1 skipped, 2 successful)
            assert result["processed"] == 3
            assert result["skipped"] >= 1


class TestRetryLogic:
    """Test retry logic with exponential backoff"""

    @pytest.mark.asyncio
    async def test_exponential_backoff(self):
        """Verify exponential backoff timing"""
        from app.utils.retry import RetryConfig

        config = RetryConfig(
            max_attempts=3,
            base_delay=1.0,
            exponential_base=2.0,
            jitter=False  # Disable jitter for predictable testing
        )

        # Attempt 0: 1.0 * (2^0) = 1.0 seconds
        assert config.get_delay(0) == 1.0

        # Attempt 1: 1.0 * (2^1) = 2.0 seconds
        assert config.get_delay(1) == 2.0

        # Attempt 2: 1.0 * (2^2) = 4.0 seconds
        assert config.get_delay(2) == 4.0

    @pytest.mark.asyncio
    async def test_retry_success_after_failures(self):
        """Test successful retry after transient failures"""
        from app.utils.retry import retry_with_backoff, RetryConfig

        call_count = 0

        async def flaky_function():
            nonlocal call_count
            call_count += 1

            if call_count < 3:
                raise litellm.RateLimitError("Rate limit")

            return "success"

        config = RetryConfig(max_attempts=3, base_delay=0.1)

        result = await retry_with_backoff(
            flaky_function,
            retryable_exceptions=(litellm.RateLimitError,),
            config=config
        )

        assert result == "success"
        assert call_count == 3
```

### 2. Integration Tests

Create `tests/integration/test_pipeline_error_handling.py`:

```python
"""
Integration tests for end-to-end error handling in pipeline
"""
import pytest
from unittest.mock import patch
import litellm
from app.services.automated_ingest_service import AutomatedIngestService
from app.database import get_database_instance


@pytest.mark.integration
class TestPipelineErrorHandling:
    """Integration tests for pipeline error handling"""

    @pytest.mark.asyncio
    async def test_invalid_api_key_stops_pipeline(self):
        """Invalid API key should stop entire pipeline immediately"""
        db = get_database_instance()
        service = AutomatedIngestService(db)

        articles = [{"uri": f"http://test{i}.com", "title": f"Test {i}"}
                   for i in range(10)]

        # Mock LLM to return AuthenticationError
        with patch('app.ai_models.LiteLLMModel.generate_response') as mock_gen:
            mock_gen.side_effect = litellm.AuthenticationError("Invalid API key")

            from app.exceptions import PipelineError, ErrorSeverity

            with pytest.raises(PipelineError) as exc_info:
                await service.process_articles_batch(articles, topic="test", keywords=[])

            # Should be fatal
            assert exc_info.value.severity == ErrorSeverity.FATAL

            # Should not have processed all articles
            # (stopped early due to fatal error)

    @pytest.mark.asyncio
    async def test_rate_limit_triggers_backoff_and_retry(self):
        """Rate limit should trigger retry with backoff, then succeed"""
        # This would require actual LiteLLM mocking or test API key
        # Placeholder for integration test
        pass

    @pytest.mark.asyncio
    async def test_large_article_skipped_gracefully(self):
        """Very large article should be skipped without crashing pipeline"""
        db = get_database_instance()
        service = AutomatedIngestService(db)

        # Create one normal article and one huge article
        articles = [
            {"uri": "http://normal.com", "title": "Normal Article", "summary": "Normal"},
            {"uri": "http://huge.com", "title": "Huge Article", "summary": "x" * 1000000},
            {"uri": "http://normal2.com", "title": "Another Normal", "summary": "Normal2"}
        ]

        result = await service.process_articles_batch(articles, topic="test", keywords=[])

        # Should have processed 3 articles (1 skipped, 2 successful or filtered)
        assert result["processed"] >= 2
        assert result.get("skipped", 0) >= 1
```

### 3. Manual Testing Checklist

#### Scenario 1: Invalid API Key
```bash
# 1. Temporarily set invalid API key
export OPENAI_API_KEY="sk-invalid-key-12345"

# 2. Run keyword monitor auto-ingest
# Expected: Pipeline stops immediately with clear error message
# Error log should show: "🚨 FATAL: Authentication failed"
# User notification: "Authentication failed - check API key"

# 3. Verify no articles were processed after error
```

#### Scenario 2: Rate Limit
```bash
# 1. Set up test to trigger rate limit (rapid API calls)
# 2. Monitor logs for retry behavior
# Expected logs:
#   "⏸️ Rate limit hit for gpt-4o-mini"
#   "Attempt 1/3 failed. Retrying in 2.00s..."
#   "Attempt 2/3 failed. Retrying in 4.00s..."
#   Either: "Success after 3 attempts" OR "Trying fallback model: gpt-3.5-turbo"

# 3. Verify articles eventually processed or failed gracefully
```

#### Scenario 3: Oversized Article
```bash
# 1. Submit article with 500,000+ characters
# 2. Monitor processing
# Expected:
#   "📏 Content too large for gpt-4o-mini"
#   "🔄 Trying fallback model: gpt-3.5-turbo-16k"
#   Either: Success with fallback OR "Article skipped (too large)"

# 3. Verify article marked as skipped in database
# 4. Verify other articles in batch still processed
```

---

## Implementation Phases

### Phase 0: Database Schema & Facade Setup
**Priority: Critical (Must Complete First)**
**AI Implementation Time: 45-60 minutes**

1. Create database migration for `llm_retry_state` table (15 minutes)
2. Add table definition to `app/database_models.py` (10 minutes)
3. Implement database facade methods in `DatabaseQueryFacade` (30 minutes):
   - `log_llm_processing_error(params)`
   - `update_article_llm_status(params)`
   - `get_llm_retry_state(model_name)`
   - `update_llm_retry_state(params)`
   - `reset_llm_retry_state(model_name)`

**Deliverables:**
- New database table created and migrated
- All required facade methods implemented and tested
- Database schema supports circuit breaker pattern

### Phase 1: Core Exception Handling
**Priority: Critical**
**AI Implementation Time: 1.5-2 hours**

1. Create `app/exceptions.py` with error classification (15 minutes)
2. Create `app/utils/retry.py` with retry logic (30 minutes)
3. Create `app/utils/circuit_breaker.py` with circuit breaker implementation (30 minutes)
4. Update `app/ai_models.py` with LiteLLM exceptions and sync retry helper (45 minutes)
5. Update `app/relevance.py` exception handling (15 minutes)
6. Update `app/analyzers/article_analyzer.py` (15 minutes)

**Deliverables:**
- All LLM calls catch specific LiteLLM exception types
- No generic `Exception` catches remain for LLM operations
- AuthenticationError stops pipeline immediately
- RateLimitError triggers retry with exponential backoff (using sync retry)
- Circuit breaker prevents cascading failures

### Phase 2: Pipeline Integration + Relevance Score Persistence Fixes
**Priority: High**
**AI Implementation Time: 1.5 hours**

**Part A: Pipeline Integration (Original)**
1. Update `automated_ingest_service.py` batch processing (30 minutes)
2. Add bail-out logic for fatal errors (15 minutes)
3. Add WebSocket notification integration (15 minutes)
4. Add error aggregation and reporting (15 minutes)

**Part B: Relevance Score Persistence Fixes (NEW)**
5. Fix exception handling in quick relevance check to save articles on failure (10 minutes)
   - Location: `automated_ingest_service.py` lines 649-652
   - Current: Sets score to 0.0 and continues processing
   - Fix: Save article with error status and skip to next article

6. Fix early-filter path to populate all three score fields (10 minutes)
   - Location: `automated_ingest_service.py` lines 630-635
   - Current: Only saves `keyword_relevance_score`
   - Fix: Populate `topic_alignment_score`, `keyword_relevance_score`, and `confidence_score`

7. Verify relevance scores saved in all code paths (10 minutes)
   - Ensure scores persist even when enrichment fails
   - Add fallback scores if relevance calculation fails during enrichment phase

**Deliverables:**
- Batch processing detects and handles specific exception types
- Fatal errors stop batch processing
- Error statistics include breakdown by type
- WebSocket notifications use correct `send_job_update()` method
- **NEW:** Relevance scores ALWAYS saved, even on failures
- **NEW:** All three score fields (topic_alignment, keyword_relevance, confidence) populated in all paths
- **NEW:** Articles with relevance check failures saved with error status
- **NEW:** No NULL relevance scores in database for processed articles

---

## Detailed Implementation Code for Phase 2 Relevance Score Fixes

### Fix 1: Exception Handling in Quick Relevance Check

**File:** `/home/orochford/tenants/testbed.aunoo.ai/app/services/automated_ingest_service.py`
**Lines:** 649-652

**Current Code (PROBLEM):**
```python
except Exception as e:
    self.logger.error(f"Quick relevance check failed for {article_uri}: {e}")
    # On error, continue with full processing as fallback
    quick_relevance_score = 0.0
```

**Updated Code (FIX):**
```python
except Exception as e:
    self.logger.error(f"Quick relevance check failed for {article_uri}: {e}")
    # Save article with error status but preserve attempt record
    article.update({
        "topic": topic,
        "ingest_status": "relevance_check_failed",
        "keyword_relevance_score": 0.0,
        "topic_alignment_score": 0.0,
        "confidence_score": 0.0,
        "overall_match_explanation": f"Relevance check failed: {str(e)}"
    })
    await self.async_db.save_below_threshold_article(article)
    self.logger.info(f"Saved article {article_uri} with relevance_check_failed status")
    continue  # Skip to next article instead of attempting enrichment
```

**Rationale:** When relevance calculation fails, we should save the article with an error status rather than proceeding with expensive enrichment that will likely also fail. This prevents wasted API calls and preserves the record that we attempted to process the article.

---

### Fix 2: Early-Filter Path Missing Score Fields

**File:** `/home/orochford/tenants/testbed.aunoo.ai/app/services/automated_ingest_service.py`
**Lines:** 630-635

**Current Code (PROBLEM):**
```python
article.update({
    "topic": topic,
    "ingest_status": "filtered_relevance",
    "keyword_relevance_score": quick_relevance_score,  # Only ONE score field
    "overall_match_explanation": quick_relevance_result.get("explanation", "")
})
await self.async_db.save_below_threshold_article(article)
```

**Updated Code (FIX):**
```python
article.update({
    "topic": topic,
    "ingest_status": "filtered_relevance",
    # Populate ALL three score fields from relevance result
    "keyword_relevance_score": quick_relevance_result.get("keyword_relevance_score", quick_relevance_score),
    "topic_alignment_score": quick_relevance_result.get("topic_alignment_score", quick_relevance_score),
    "confidence_score": quick_relevance_result.get("confidence_score", quick_relevance_score),
    "overall_match_explanation": quick_relevance_result.get("explanation", "")
})
await self.async_db.save_below_threshold_article(article)
```

**Rationale:** The `RelevanceCalculator.analyze_relevance()` method returns multiple score fields. We should save all of them, not just one. This ensures the database has complete relevance data even for filtered articles.

---

### Fix 3: Ensure RelevanceCalculator Returns All Score Fields

**File:** `/home/orochford/tenants/testbed.aunoo.ai/app/relevance.py`
**Method:** `analyze_relevance()`

**Verify the return structure includes:**
```python
return {
    "relevance_score": combined_score,  # Average of topic + keyword
    "topic_alignment_score": topic_alignment_score,
    "keyword_relevance_score": keyword_relevance_score,
    "confidence_score": confidence_score,
    "explanation": explanation_text,
    # ... other fields
}
```

**If missing, update the return statement to include all three scores.** This ensures downstream code can extract individual scores, not just the combined average.

---

### Fix 4: Verify Final Relevance Save Path

**File:** `/home/orochford/tenants/testbed.aunoo.ai/app/services/automated_ingest_service.py`
**Lines:** 736-821

**Verification Checklist:**

1. **After enrichment relevance calculation (line ~736):**
   ```python
   relevance_result = await self.relevance_calculator.analyze_relevance(...)
   relevance_score = relevance_result.get("relevance_score", 0.0)

   # ENSURE we also extract the individual scores
   enriched_article.update({
       "topic_alignment_score": relevance_result.get("topic_alignment_score", 0.0),
       "keyword_relevance_score": relevance_result.get("keyword_relevance_score", 0.0),
       "confidence_score": relevance_result.get("confidence_score", 0.0),
       "overall_match_explanation": relevance_result.get("explanation", "")
   })
   ```

2. **Below-threshold save path (line ~821):**
   ```python
   # VERIFY all score fields are present in enriched_article before save
   await self.async_db.save_below_threshold_article(enriched_article)
   ```

3. **Approved article save path (line ~769):**
   ```python
   # VERIFY all score fields are present in enriched_article before save
   success = await self.async_db.update_article_with_enrichment(enriched_article)
   ```

**Add fallback logic if relevance calculation fails during enrichment:**
```python
try:
    relevance_result = await self.relevance_calculator.analyze_relevance(...)
    relevance_score = relevance_result.get("relevance_score", 0.0)
except Exception as e:
    self.logger.error(f"Final relevance calculation failed for {article_uri}: {e}")
    # Use fallback scores so we don't lose the enrichment work
    relevance_score = 0.0
    relevance_result = {
        "relevance_score": 0.0,
        "topic_alignment_score": 0.0,
        "keyword_relevance_score": 0.0,
        "confidence_score": 0.0,
        "explanation": f"Final relevance calculation failed: {str(e)}"
    }
```

**Rationale:** Even if the final relevance calculation fails after enrichment, we should save the enriched article with fallback scores rather than losing all the enrichment work (bias data, scraped content, LLM analysis).

---

### Testing Checklist for Relevance Score Fixes

**Test Case 1: Quick Relevance Check Fails**
- Mock `_score_article_relevance_async()` to raise an exception
- Verify article is saved with `ingest_status = "relevance_check_failed"`
- Verify all three score fields are set to 0.0
- Verify processing skips to next article (no enrichment attempted)

**Test Case 2: Early Filter Path**
- Process article that scores below threshold in quick check
- Verify all three score fields (topic_alignment, keyword_relevance, confidence) are populated
- Verify values come from `quick_relevance_result` dictionary

**Test Case 3: Final Relevance Calculation Fails**
- Mock final relevance calculation to raise exception after enrichment
- Verify article is still saved (not lost)
- Verify fallback scores are used
- Verify enrichment data (bias, content, analysis) is preserved

**Test Case 4: Database Query for NULL Scores**
- After processing batch, query database:
  ```sql
  SELECT COUNT(*) FROM articles
  WHERE ingest_status IN ('filtered_relevance', 'relevance_check_failed', 'approved')
    AND (topic_alignment_score IS NULL
         OR keyword_relevance_score IS NULL
         OR confidence_score IS NULL);
  ```
- Expected result: 0 rows (no NULLs)

---

### Phase 3: Testing
**Priority: High**
**AI Implementation Time: 2-2.5 hours**

1. Write unit tests for exception handling (45 minutes)
2. Write unit tests for circuit breaker (30 minutes)
3. Write integration tests (45 minutes)
4. Document manual testing procedures (15 minutes)

**Deliverables:**
- All tests pass
- Coverage > 80% for new exception handling code
- Circuit breaker state transitions tested
- Manual test scenarios documented

### Phase 4: Documentation
**Priority: Medium**
**AI Implementation Time: 30-45 minutes**

1. Document relevance scores in UI tooltips (10 minutes)
2. Create `docs/ERROR_HANDLING.md` (15 minutes)
3. Add inline code comments explaining exception strategy (10 minutes)
4. Update developer documentation (10 minutes)

**Deliverables:**
- Users understand three score types
- Developers understand exception handling strategy
- Circuit breaker pattern documented
- Error troubleshooting guide available

**Total Implementation Time: 5.5-7 hours**

---

## Success Criteria

### Functional Requirements
- ✅ All LLM calls catch specific LiteLLM exception types (not generic `Exception`)
- ✅ `AuthenticationError` stops pipeline immediately with clear message
- ✅ `RateLimitError` triggers retry with exponential backoff (3 attempts)
- ✅ `ContextWindowExceededError` skips article without failing batch
- ✅ `ServiceUnavailableError` tries fallback model
- ✅ Unknown exceptions treated as fatal (fail-safe)

### Non-Functional Requirements
- ✅ No string-based error detection remains
- ✅ All exception handlers have logging
- ✅ Error messages are user-friendly (no stack traces exposed)
- ✅ Batch processing doesn't lose successful results on partial failure
- ✅ Pipeline provides clear indication of why processing stopped

### Testing Requirements
- ✅ Unit test coverage > 80% for exception handling code
- ✅ Integration tests verify end-to-end behavior
- ✅ Manual testing confirms expected behavior for all error scenarios

### Documentation Requirements
- ✅ Code comments explain exception handling strategy
- ✅ Developer documentation describes error severity levels
- ✅ User documentation explains relevance scores
- ✅ Troubleshooting guide for common errors

---

## Risk Assessment

### High Risk

**1. Breaking Change to Error Handling**
- **Risk:** Existing code expects string error messages, not exceptions
- **Mitigation:** Thorough testing, gradual rollout with feature flag
- **Rollback:** Keep old code commented for quick revert

**2. LiteLLM Exception Type Changes**
- **Risk:** LiteLLM updates could change exception types
- **Mitigation:** Pin LiteLLM version, monitor release notes
- **Rollback:** Version lock in requirements.txt

### Medium Risk

**3. Retry Logic Causing Delays**
- **Risk:** Exponential backoff could slow pipeline significantly
- **Mitigation:** Tune retry config, add timeout limits
- **Monitoring:** Track retry counts and delays

**4. Fallback Model Costs**
- **Risk:** Excessive fallback usage increases API costs
- **Mitigation:** Track fallback usage, set cost alerts
- **Monitoring:** Log fallback frequency

### Low Risk

**5. User Confusion About Scores**
- **Risk:** Users don't understand three different scores
- **Mitigation:** Add tooltips, help text, documentation
- **Support:** FAQ entry explaining scores

---

## Rollback Plan

If critical issues arise during deployment:

1. **Immediate Rollback (< 5 minutes)**
   ```bash
   git revert <commit-hash>
   git push
   systemctl restart aunoo-api
   ```

2. **Feature Flag Disable (< 1 minute)**
   ```python
   # In app/config/feature_flags.py
   USE_LITELLM_EXCEPTIONS = False  # Revert to old behavior
   ```

3. **Database Rollback**
   - No database schema changes in this spec
   - No data migration required

4. **Monitoring After Rollback**
   - Verify error rate returns to baseline
   - Check no articles stuck in processing
   - Confirm API costs return to normal

---

## Appendix A: Code Style Guide

### Exception Handling Pattern

```python
# ✅ GOOD: Specific exceptions, clear severity
try:
    result = llm_call()
except AuthenticationError as e:
    logger.error(f"🚨 FATAL: {e}")
    raise PipelineError(..., severity=ErrorSeverity.FATAL)
except RateLimitError as e:
    logger.warning(f"⏸️ Rate limit: {e}")
    # Retry logic
except ContextWindowExceededError as e:
    logger.warning(f"📏 Content too large: {e}")
    return default_value
except Exception as e:
    logger.error(f"🚨 Unexpected: {e}")
    raise PipelineError(..., severity=ErrorSeverity.FATAL)

# ❌ BAD: Generic exception, string detection
try:
    result = llm_call()
except Exception as e:
    if "rate limit" in str(e).lower():
        # This is fragile!
```

### Logging Emoji Convention

- 🚨 Fatal errors (AuthenticationError, unknown errors)
- ⏸️ Rate limits (recoverable with wait)
- 📏 Content size issues (ContextWindowExceededError)
- 🔄 Retry/fallback attempts
- ✅ Success after retry
- ❌ Final failure after retries
- ⏱️ Timeouts
- 🔌 Network errors

### Error Message Format

```python
# User-facing messages (returned in API response)
"Error: Content exceeds maximum length for gpt-4o-mini. Please reduce content size."

# Developer logs (with context)
logger.error(f"Content too large for {self.model_name}: {article_uri}")

# Exception messages (for re-raising)
raise PipelineError(
    f"Authentication failed - invalid API key for {self.model_name}",
    severity=ErrorSeverity.FATAL,
    original_exception=e
)
```

---

## Appendix B: Configuration

### Retry Configuration

Default retry config in `app/config/llm_config.py`:

```python
"""
LLM error handling configuration
"""
from app.utils.retry import RetryConfig

# Rate limit retry configuration
RATE_LIMIT_RETRY_CONFIG = RetryConfig(
    max_attempts=3,
    base_delay=2.0,      # Start with 2 second delay
    max_delay=60.0,      # Cap at 60 seconds
    exponential_base=2.0,
    jitter=True
)

# Network error retry configuration
NETWORK_ERROR_RETRY_CONFIG = RetryConfig(
    max_attempts=2,
    base_delay=1.0,
    max_delay=10.0,
    exponential_base=2.0,
    jitter=True
)

# Fallback model priority
FALLBACK_MODELS = {
    "gpt-4o": ["gpt-4o-mini", "gpt-3.5-turbo"],
    "gpt-4o-mini": ["gpt-3.5-turbo"],
    "claude-3-5-sonnet-20241022": ["claude-3-haiku-20240307"],
}
```

### Environment Variables

```bash
# Enable/disable specific error handling features
ENABLE_LLM_RETRY=true
ENABLE_FALLBACK_MODELS=true
MAX_RETRY_ATTEMPTS=3
RETRY_BASE_DELAY=2.0

# Feature flag for gradual rollout
USE_LITELLM_EXCEPTIONS=true
```

---

**End of Specification**
