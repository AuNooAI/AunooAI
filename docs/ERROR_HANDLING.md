# LLM Error Handling - Developer Guide

**Version:** 1.0
**Date:** 2025-01-18
**Status:** Production Ready

## Overview

This document provides a comprehensive guide for developers working with the LLM error handling system. It covers exception types, error handling patterns, circuit breaker usage, retry strategies, and best practices.

---

## Table of Contents

1. [Architecture Overview](#architecture-overview)
2. [Exception Classification](#exception-classification)
3. [Using the Error Handling System](#using-the-error-handling-system)
4. [Circuit Breaker Pattern](#circuit-breaker-pattern)
5. [Retry Strategies](#retry-strategies)
6. [Best Practices](#best-practices)
7. [Common Patterns](#common-patterns)
8. [Debugging and Troubleshooting](#debugging-and-troubleshooting)

---

## Architecture Overview

The LLM error handling system consists of four main components:

```
┌─────────────────────────────────────────────────────┐
│              Application Layer                       │
│  (automated_ingest_service, article_analyzer, etc)  │
└─────────────────┬───────────────────────────────────┘
                  │
                  ▼
┌─────────────────────────────────────────────────────┐
│            AI Models Layer (ai_models.py)            │
│  - LiteLLM exception handling                       │
│  - Retry logic                                       │
│  - Fallback models                                   │
└─────────────────┬───────────────────────────────────┘
                  │
        ┌─────────┼─────────┐
        ▼         ▼         ▼
┌──────────┐ ┌──────────┐ ┌─────────────┐
│Exception │ │  Retry   │ │   Circuit   │
│Classifier│ │  Logic   │ │   Breaker   │
└──────────┘ └──────────┘ └─────────────┘
        │         │              │
        └─────────┼──────────────┘
                  ▼
        ┌──────────────────┐
        │     Database     │
        │  (Error Logging) │
        └──────────────────┘
```

### Key Components

1. **Exception Classifier** (`app/exceptions.py`)
   - Categorizes LiteLLM exceptions into severity levels
   - Determines retry strategy

2. **Retry Logic** (`app/utils/retry.py`)
   - Implements exponential backoff
   - Supports both sync and async operations

3. **Circuit Breaker** (`app/utils/circuit_breaker.py`)
   - Prevents cascading failures
   - Database-backed persistent state

4. **Database Layer** (`app/database_query_facade.py`)
   - Logs errors for monitoring
   - Stores circuit breaker state
   - Updates article LLM status

---

## Exception Classification

### Error Severity Levels

The system classifies all errors into four severity levels:

```python
from app.exceptions import ErrorSeverity

ErrorSeverity.FATAL       # Stop pipeline immediately (no retry, no fallback)
ErrorSeverity.RECOVERABLE # Retry with exponential backoff
ErrorSeverity.SKIPPABLE   # Skip retry, try fallback models
ErrorSeverity.DEGRADED    # Try fallback models immediately
```

### LiteLLM Exception Mapping

#### FATAL (Pipeline-Stopping Errors)
```python
# These errors stop the pipeline immediately
litellm.AuthenticationError     # Invalid API key
litellm.BudgetExceededError     # Budget/quota exceeded
```

**Handling:** Raise `PipelineError` immediately, no retries or fallbacks.

#### RECOVERABLE (Retry-Eligible Errors)
```python
# These errors trigger retry with exponential backoff
litellm.RateLimitError          # API rate limit exceeded
litellm.Timeout                 # Request timeout
litellm.APIConnectionError      # Network connection issues
```

**Handling:** Retry up to 3 times with exponential backoff, then try fallback models.

#### SKIPPABLE (Bypass-Eligible Errors)
```python
# These errors skip retry and go straight to fallback
litellm.ContextWindowExceededError  # Context too large
litellm.BadRequestError             # Malformed request
litellm.InvalidRequestError         # Invalid parameters
litellm.JSONSchemaValidationError   # Response format error
```

**Handling:** Skip primary model, try fallback models immediately.

#### DEGRADED (Fallback-Eligible Errors)
```python
# These errors try fallback models
litellm.ServiceUnavailableError  # Service temporarily down
litellm.APIError                 # Generic API error
```

**Handling:** Try fallback models, may retry fallback if configured.

---

## Using the Error Handling System

### Basic Pattern

All LLM operations should use this pattern:

```python
from app.exceptions import PipelineError, ErrorSeverity, LLMErrorClassifier
import logging

logger = logging.getLogger(__name__)

def your_llm_function():
    try:
        # Call LLM (this handles errors internally)
        result = ai_model.generate_response(messages)
        return result

    except PipelineError as e:
        # Fatal error - log and propagate
        logger.error(f"🚨 FATAL error: {e.severity.value} - {e.message}")
        # Re-raise to let caller handle (e.g., stop pipeline)
        raise

    except Exception as e:
        # Unexpected error - log and handle gracefully
        logger.error(f"⚠️ Unexpected error: {str(e)}")
        # Return default or re-raise based on context
        return default_value
```

### In Article Analysis

```python
# app/analyzers/article_analyzer.py

def analyze_content(self, title, article_text, source):
    """Analyze article content with error handling."""

    try:
        # Generate response (handles LiteLLM errors internally)
        response_text = self.ai_model.generate_response(messages)

        # Parse and return results
        return self._parse_response(response_text)

    except PipelineError as e:
        # Fatal error - re-raise to stop pipeline
        logger.error(f"🚨 FATAL error during analysis: {e}")
        raise

    except Exception as e:
        # Non-fatal error - return degraded result
        logger.error(f"⚠️ Analysis failed: {str(e)}")
        return {
            "summary": "Analysis unavailable",
            "sentiment": "neutral",
            "error": str(e)
        }
```

### In Relevance Calculation

```python
# app/relevance.py

def analyze_relevance(self, title, source, content, topic, keywords):
    """Analyze relevance with error handling."""

    try:
        # Generate response (handles errors internally)
        response_text = self.ai_model.generate_response(messages)

        # Parse JSON response
        result = json.loads(response_text)

        return {
            "topic_alignment_score": result["topic_alignment_score"],
            "keyword_relevance_score": result["keyword_relevance_score"],
            "confidence_score": result["confidence_score"]
        }

    except PipelineError as e:
        # Fatal error - propagate to caller
        logger.error(f"🚨 FATAL error during relevance analysis: {e}")
        raise

    except (json.JSONDecodeError, KeyError) as e:
        # Parsing error - return default scores
        logger.error(f"Failed to parse relevance response: {e}")
        return {
            "topic_alignment_score": 0.0,
            "keyword_relevance_score": 0.0,
            "confidence_score": 0.0,
            "error": str(e)
        }
```

### In Automated Ingest Service

```python
# app/services/automated_ingest_service.py

async def process_article(self, article, topic, keywords):
    """Process article with comprehensive error handling."""

    try:
        # Perform relevance check
        relevance_result = self.relevance_calculator.analyze_relevance(
            title=article.get("title"),
            source=article.get("source"),
            content=article.get("content"),
            topic=topic,
            keywords=keywords
        )

        # CRITICAL: Always save all three scores
        article.update({
            "topic_alignment_score": relevance_result.get("topic_alignment_score", 0.0),
            "keyword_relevance_score": relevance_result.get("keyword_relevance_score", 0.0),
            "confidence_score": relevance_result.get("confidence_score", 0.0),
            "overall_match_explanation": relevance_result.get("overall_match_explanation", "")
        })

        # Filter or process based on scores
        if relevance_result["relevance_score"] < threshold:
            article["ingest_status"] = "filtered_relevance"
            await self.db.save_below_threshold_article(article)
        else:
            # Continue processing
            pass

    except PipelineError as e:
        # Fatal error - save article with error status
        logger.error(f"🚨 FATAL error processing {article['uri']}: {e}")

        article.update({
            "ingest_status": "relevance_check_failed",
            "topic_alignment_score": 0.0,
            "keyword_relevance_score": 0.0,
            "confidence_score": 0.0,
            "overall_match_explanation": f"Fatal error: {e.message}"
        })

        await self.db.save_below_threshold_article(article)
        # Do NOT re-raise - continue with next article

    except Exception as e:
        # Unexpected error - log and save with error status
        logger.error(f"⚠️ Unexpected error processing {article['uri']}: {e}")

        article.update({
            "ingest_status": "relevance_check_failed",
            "topic_alignment_score": 0.0,
            "keyword_relevance_score": 0.0,
            "confidence_score": 0.0,
            "overall_match_explanation": f"Error: {str(e)}"
        })

        await self.db.save_below_threshold_article(article)
```

---

## Circuit Breaker Pattern

### Overview

The circuit breaker prevents cascading failures by:
1. Tracking consecutive failures per model
2. Opening circuit after threshold (5 failures)
3. Blocking requests when circuit is OPEN
4. Attempting recovery after timeout (5 minutes)

### Circuit States

```
┌──────────┐
│  CLOSED  │  ◄── Normal operation, all requests allowed
└────┬─────┘
     │ Failure threshold reached (5 failures)
     ▼
┌──────────┐
│   OPEN   │  ◄── Blocking requests, preventing load
└────┬─────┘
     │ Timeout elapsed (5 minutes)
     ▼
┌──────────┐
│HALF_OPEN │  ◄── Testing recovery, limited requests
└────┬─────┘
     │ Success → CLOSED
     │ Failure → OPEN
```

### Using Circuit Breaker

Circuit breaker is automatically integrated into `LiteLLMModel`:

```python
from app.ai_models import LiteLLMModel

# Circuit breaker is initialized automatically
model = LiteLLMModel.get_instance("gpt-4")

# Circuit breaker is checked on every generate_response() call
try:
    response = model.generate_response(messages)
except PipelineError as e:
    if "circuit breaker" in str(e).lower():
        # Circuit is OPEN - model is temporarily unavailable
        logger.warning(f"Circuit breaker OPEN for {model.model_name}")
        # Use fallback or wait
```

### Manual Circuit Breaker Control

```python
from app.utils.circuit_breaker import CircuitBreaker

# Get circuit breaker for a model
cb = CircuitBreaker(model_name="gpt-4")

# Check if circuit allows request
try:
    if cb.check_circuit():
        # Circuit is closed, proceed with request
        pass
except CircuitBreakerOpen as e:
    # Circuit is open, request blocked
    logger.warning(f"Circuit open: {e}")

# Record success (closes circuit, resets failures)
cb.record_success()

# Record failure (may open circuit)
cb.record_failure(error)

# Manually reset circuit breaker
cb.reset()
```

### Monitoring Circuit Breaker State

```sql
-- Check circuit breaker states
SELECT model_name,
       circuit_state,
       consecutive_failures,
       last_failure_time,
       last_success_time
FROM llm_retry_state
ORDER BY last_updated DESC;

-- Find models with open circuits
SELECT model_name, circuit_opened_at,
       EXTRACT(EPOCH FROM (NOW() - circuit_opened_at)) as seconds_open
FROM llm_retry_state
WHERE circuit_state = 'open';
```

---

## Retry Strategies

### Exponential Backoff Configuration

```python
from app.utils.retry import RetryConfig, retry_sync_with_backoff

# Default configuration
config = RetryConfig(
    max_attempts=3,        # Maximum retry attempts
    base_delay=1.0,        # Initial delay in seconds
    max_delay=60.0,        # Maximum delay cap
    exponential_base=2.0,  # Exponential multiplier
    jitter=True            # Add randomness to delays
)

# Custom configuration for aggressive retries
aggressive_config = RetryConfig(
    max_attempts=5,
    base_delay=0.5,
    max_delay=30.0,
    exponential_base=1.5,
    jitter=True
)

# Custom configuration for patient retries
patient_config = RetryConfig(
    max_attempts=3,
    base_delay=5.0,
    max_delay=300.0,
    exponential_base=3.0,
    jitter=True
)
```

### Delay Calculation

With default config:
- Attempt 1: Immediate
- Attempt 2: 1.0s delay (base_delay × 2^0)
- Attempt 3: 2.0s delay (base_delay × 2^1)

With jitter enabled:
- Delays vary randomly within ±50% of calculated value
- Prevents thundering herd problem

### Synchronous Retry

```python
from app.utils.retry import retry_sync_with_backoff, RetryConfig
import litellm

def call_llm(messages):
    """Call LLM with potential errors."""
    return litellm.completion(model="gpt-4", messages=messages)

# Retry with exponential backoff
config = RetryConfig(max_attempts=3, base_delay=1.0)

try:
    result = retry_sync_with_backoff(
        call_llm,
        messages=[{"role": "user", "content": "Hello"}],
        retryable_exceptions=(
            litellm.RateLimitError,
            litellm.Timeout,
            litellm.APIConnectionError
        ),
        config=config
    )
except RetryError as e:
    # All retry attempts failed
    logger.error(f"Retry failed after {e.attempt_count} attempts")
    logger.error(f"Last error: {e.last_exception}")
```

### Asynchronous Retry

```python
from app.utils.retry import retry_async_with_backoff, RetryConfig

async def call_llm_async(messages):
    """Async LLM call."""
    return await some_async_llm_call(messages)

# Async retry
config = RetryConfig(max_attempts=3)

try:
    result = await retry_async_with_backoff(
        call_llm_async,
        messages=[{"role": "user", "content": "Hello"}],
        retryable_exceptions=(RateLimitError, Timeout),
        config=config
    )
except RetryError as e:
    logger.error(f"Async retry failed: {e}")
```

### Retry with Callback

```python
from app.utils.retry import retry_sync_with_backoff

def on_retry_callback(attempt, error, delay):
    """Called before each retry."""
    logger.warning(f"Retry attempt {attempt} after {delay}s due to: {error}")

result = retry_sync_with_backoff(
    call_llm,
    messages=messages,
    retryable_exceptions=(RateLimitError,),
    config=config,
    on_retry=on_retry_callback
)
```

---

## Best Practices

### 1. Always Re-raise PipelineError

```python
# ✅ CORRECT
try:
    result = ai_model.generate_response(messages)
except PipelineError as e:
    logger.error(f"Fatal error: {e}")
    raise  # Re-raise to stop pipeline

# ❌ INCORRECT
try:
    result = ai_model.generate_response(messages)
except PipelineError as e:
    logger.error(f"Fatal error: {e}")
    return None  # Don't swallow fatal errors!
```

### 2. Always Save Relevance Scores

```python
# ✅ CORRECT - Save all three scores
article.update({
    "topic_alignment_score": result.get("topic_alignment_score", 0.0),
    "keyword_relevance_score": result.get("keyword_relevance_score", 0.0),
    "confidence_score": result.get("confidence_score", 0.0)
})

# ❌ INCORRECT - Missing scores
article.update({
    "topic_alignment_score": result.get("topic_alignment_score", 0.0)
    # Missing keyword_relevance_score and confidence_score!
})
```

### 3. Use Appropriate Error Severity

```python
# ✅ CORRECT - Fatal error stops pipeline
if error_type == "auth_error":
    raise PipelineError(
        message="Authentication failed",
        original_error=e,
        severity=ErrorSeverity.FATAL
    )

# ❌ INCORRECT - Fatal error treated as degraded
if error_type == "auth_error":
    logger.warning("Auth failed, trying fallback")
    # Should stop pipeline, not continue!
```

### 4. Log with Appropriate Severity

```python
# ✅ CORRECT - Clear severity indicators
logger.error("🚨 FATAL: Authentication failed")
logger.warning("⚠️ RECOVERABLE: Rate limit exceeded, retrying")
logger.info("ℹ️ SKIPPABLE: Context too large, trying fallback")

# ❌ INCORRECT - Ambiguous logging
logger.error("Error occurred")  # What kind? What severity?
```

### 5. Provide Context in Errors

```python
# ✅ CORRECT - Rich context
raise PipelineError(
    message=f"Failed to analyze article: {article_uri}",
    original_error=e,
    severity=ErrorSeverity.FATAL,
    model_name="gpt-4",
    article_uri=article_uri,
    context={"topic": topic, "keywords": keywords}
)

# ❌ INCORRECT - Minimal context
raise PipelineError(
    message="Error",
    original_error=e,
    severity=ErrorSeverity.FATAL
)
```

### 6. Handle Both Sync and Async Correctly

```python
# ✅ CORRECT - Use sync retry for sync functions
def sync_function():
    return retry_sync_with_backoff(...)  # Uses time.sleep()

# ✅ CORRECT - Use async retry for async functions
async def async_function():
    return await retry_async_with_backoff(...)  # Uses asyncio.sleep()

# ❌ INCORRECT - Mixing sync/async
async def async_function():
    return retry_sync_with_backoff(...)  # Will cause event loop issues!
```

### 7. Configure Retries Appropriately

```python
# ✅ CORRECT - Aggressive retries for transient errors
if error_type == RateLimitError:
    config = RetryConfig(
        max_attempts=5,      # More attempts
        base_delay=2.0,      # Longer delays
        max_delay=120.0
    )

# ✅ CORRECT - Quick retries for connection errors
if error_type == APIConnectionError:
    config = RetryConfig(
        max_attempts=3,
        base_delay=0.5,      # Faster retry
        max_delay=10.0
    )
```

---

## Common Patterns

### Pattern 1: Batch Processing with Error Handling

```python
async def process_batch(articles, topic, keywords):
    """Process multiple articles with error handling."""

    successful = []
    failed = []

    for article in articles:
        try:
            result = await process_article(article, topic, keywords)
            successful.append(result)

        except PipelineError as e:
            # Fatal error - log and continue with next article
            logger.error(f"Fatal error for {article['uri']}: {e}")
            failed.append({
                "article": article,
                "error": str(e),
                "severity": e.severity.value
            })
            # Don't break - continue processing other articles

        except Exception as e:
            # Unexpected error - log and continue
            logger.error(f"Unexpected error for {article['uri']}: {e}")
            failed.append({
                "article": article,
                "error": str(e),
                "severity": "unknown"
            })

    return {
        "successful": successful,
        "failed": failed,
        "total": len(articles),
        "success_rate": len(successful) / len(articles)
    }
```

### Pattern 2: Graceful Degradation

```python
def analyze_article_with_degradation(article):
    """Analyze article with graceful degradation."""

    try:
        # Try full analysis
        return full_analysis(article)

    except PipelineError as e:
        if e.severity == ErrorSeverity.FATAL:
            # Fatal error - no degradation possible
            raise

        logger.warning("Full analysis failed, trying basic analysis")

        try:
            # Try simpler analysis
            return basic_analysis(article)

        except Exception:
            # Even basic analysis failed - return minimal result
            logger.error("All analysis failed, returning minimal result")
            return {
                "summary": article.get("title", "No summary available"),
                "sentiment": "neutral",
                "error": "Analysis unavailable"
            }
```

### Pattern 3: Fallback Model Chain

```python
def generate_with_fallbacks(messages, primary_model, fallback_models):
    """Try primary model, then fallbacks in order."""

    models_to_try = [primary_model] + fallback_models

    for model_name in models_to_try:
        try:
            model = LiteLLMModel.get_instance(model_name)
            result = model.generate_response(messages)
            logger.info(f"✅ Success with model: {model_name}")
            return result

        except PipelineError as e:
            if e.severity == ErrorSeverity.FATAL:
                # Fatal error - don't try fallbacks
                logger.error(f"Fatal error with {model_name}, stopping")
                raise

            logger.warning(f"Failed with {model_name}, trying next fallback")
            continue

    # All models failed
    raise PipelineError(
        message="All models failed",
        severity=ErrorSeverity.FATAL
    )
```

### Pattern 4: Error Recovery with Notification

```python
def process_with_notification(article, notify_callback=None):
    """Process article and notify on errors."""

    try:
        result = process_article(article)
        return result

    except PipelineError as e:
        # Log error
        logger.error(f"Fatal error: {e}")

        # Notify if callback provided
        if notify_callback:
            notify_callback({
                "article_uri": article["uri"],
                "error_type": type(e.original_error).__name__,
                "severity": e.severity.value,
                "message": e.message,
                "timestamp": datetime.now()
            })

        # Re-raise or return default based on severity
        if e.severity == ErrorSeverity.FATAL:
            raise
        else:
            return default_result()
```

---

## Debugging and Troubleshooting

### Enable Debug Logging

```python
import logging

# Enable debug logging for error handling components
logging.getLogger('app.exceptions').setLevel(logging.DEBUG)
logging.getLogger('app.utils.retry').setLevel(logging.DEBUG)
logging.getLogger('app.utils.circuit_breaker').setLevel(logging.DEBUG)
logging.getLogger('app.ai_models').setLevel(logging.DEBUG)
```

### Check Error Logs

```bash
# View recent errors
tail -f /var/log/aunoo/backend.log | grep "🚨"

# View retry attempts
tail -f /var/log/aunoo/backend.log | grep "Retrying"

# View circuit breaker events
tail -f /var/log/aunoo/backend.log | grep "circuit"
```

### Database Diagnostics

```sql
-- Recent errors by severity
SELECT severity, COUNT(*) as count
FROM llm_processing_errors
WHERE timestamp > NOW() - INTERVAL '1 hour'
GROUP BY severity;

-- Models with open circuits
SELECT model_name, circuit_opened_at,
       EXTRACT(EPOCH FROM (NOW() - circuit_opened_at))/60 as minutes_open
FROM llm_retry_state
WHERE circuit_state = 'open';

-- Error frequency by type
SELECT error_type, COUNT(*) as count,
       AVG(retry_count) as avg_retries
FROM llm_processing_errors
WHERE timestamp > NOW() - INTERVAL '24 hours'
GROUP BY error_type
ORDER BY count DESC;
```

### Common Issues and Solutions

#### Issue: Circuit Breaker Stuck Open
```sql
-- Reset specific circuit breaker
DELETE FROM llm_retry_state WHERE model_name = 'gpt-4';
```

#### Issue: Relevance Scores Not Saving
```python
# Verify all three scores are being set
logger.debug(f"Scores: topic={topic_score}, keyword={keyword_score}, confidence={confidence_score}")
```

#### Issue: Retries Not Working
```python
# Check if error is retryable
from app.exceptions import LLMErrorClassifier
severity, should_retry = LLMErrorClassifier.classify_error(error)
logger.debug(f"Error classified as {severity.value}, should_retry={should_retry}")
```

---

## Summary

**Key Takeaways:**

1. **Always re-raise `PipelineError`** - Don't swallow fatal errors
2. **Save all three relevance scores** - topic_alignment, keyword_relevance, confidence
3. **Let `ai_models.py` handle exceptions** - Don't catch LiteLLM errors in calling code
4. **Use appropriate retry strategies** - Exponential backoff for recoverable errors
5. **Monitor circuit breaker state** - Watch for models with open circuits
6. **Log with clear severity** - Use 🚨 for fatal, ⚠️ for recoverable, ℹ️ for skippable
7. **Provide rich context** - Include article URI, model name, and error details

---

**Related Documentation:**
- Implementation Spec: `docs/IMPLEMENTATION_SPEC_LLM_ERROR_HANDLING.md`
- Manual Testing Guide: `docs/LLM_ERROR_HANDLING_MANUAL_TESTING.md`
- Deployment Guide: `docs/LLM_ERROR_HANDLING_IMPLEMENTATION_COMPLETE.md`

---

**Version:** 1.0
**Last Updated:** 2025-01-18
**Status:** Production Ready
