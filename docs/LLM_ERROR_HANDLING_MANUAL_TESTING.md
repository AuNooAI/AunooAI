# LLM Error Handling - Manual Testing Procedures

**Version:** 1.0
**Date:** 2025-01-18
**Status:** Complete

## Overview

This document provides comprehensive manual testing procedures for the LLM error handling implementation, including exception classification, retry logic, circuit breaker pattern, and relevance score persistence.

---

## Table of Contents

1. [Prerequisites](#prerequisites)
2. [Test Environment Setup](#test-environment-setup)
3. [Unit Test Execution](#unit-test-execution)
4. [Integration Testing](#integration-testing)
5. [Circuit Breaker Testing](#circuit-breaker-testing)
6. [Relevance Score Persistence Testing](#relevance-score-persistence-testing)
7. [Error Recovery Testing](#error-recovery-testing)
8. [Monitoring and Verification](#monitoring-and-verification)
9. [Troubleshooting](#troubleshooting)

---

## Prerequisites

### Required Tools
- Python 3.10+
- pytest
- PostgreSQL client (psql)
- Access to testbed database

### Environment Variables
Ensure the following environment variables are set:

```bash
DB_TYPE=postgresql
DB_USER=test_user
DB_NAME=test
DB_HOST=localhost
PGPASSWORD=<your_password>
```

### Database Setup
Verify the LLM error handling tables exist:

```bash
PGPASSWORD='<password>' psql -U test_user -d test -h localhost -c "\dt llm_*"
```

Expected output:
- `llm_retry_state`
- `llm_processing_errors`
- `processing_jobs` (optional)

---

## Test Environment Setup

### 1. Activate Virtual Environment

```bash
cd /home/orochford/tenants/testbed.aunoo.ai
source .venv/bin/activate
```

### 2. Install Test Dependencies

```bash
pip install pytest pytest-asyncio pytest-mock
```

### 3. Verify Database Connection

```bash
python -c "from app.database_query_facade import DatabaseQueryFacade; db = DatabaseQueryFacade(); print('Database connection: OK')"
```

---

## Unit Test Execution

### Run All LLM Error Handling Tests

```bash
# Run all new tests
pytest tests/test_exceptions.py tests/test_retry.py tests/test_circuit_breaker.py tests/test_ai_models_error_handling.py -v

# Run with coverage report
pytest tests/test_exceptions.py tests/test_retry.py tests/test_circuit_breaker.py tests/test_ai_models_error_handling.py --cov=app.exceptions --cov=app.utils.retry --cov=app.utils.circuit_breaker --cov=app.ai_models -v
```

### Run Individual Test Suites

#### Exception Classification Tests
```bash
pytest tests/test_exceptions.py -v
```

**Expected Results:**
- All `ErrorSeverity` enum tests pass
- All `LLMErrorClassifier` tests pass
- All `PipelineError` tests pass
- Total: ~30-40 tests

#### Retry Logic Tests
```bash
pytest tests/test_retry.py -v
```

**Expected Results:**
- Exponential backoff tests pass
- Jitter tests pass
- Max attempts tests pass
- Both sync and async tests pass
- Total: ~20-30 tests

#### Circuit Breaker Tests
```bash
pytest tests/test_circuit_breaker.py -v
```

**Expected Results:**
- State transition tests pass (CLOSED → OPEN → HALF_OPEN → CLOSED)
- Failure threshold tests pass
- Timeout tests pass
- Database persistence tests pass
- Total: ~30-40 tests

#### AI Models Error Handling Integration Tests
```bash
pytest tests/test_ai_models_error_handling.py -v
```

**Expected Results:**
- Fatal error handling tests pass
- Recoverable error retry tests pass
- Skippable error handling tests pass
- Fallback model tests pass
- Total: ~25-35 tests

---

## Integration Testing

### Test 1: Article Analysis with Error Injection

This test verifies that article analysis handles errors gracefully.

#### Setup: Create Test Script

Create `scripts/test_error_handling_integration.py`:

```python
import asyncio
from app.analyzers.article_analyzer import ArticleAnalyzer
from app.ai_models import LiteLLMModel
from app.exceptions import PipelineError

async def test_article_analysis():
    """Test article analysis with a real article."""

    # Initialize with a model
    model = LiteLLMModel.get_instance("gpt-4")
    analyzer = ArticleAnalyzer(model)

    test_article = """
    Artificial Intelligence Breakthrough: New Model Achieves
    Human-Level Performance. Researchers at leading AI lab have
    developed a groundbreaking model that demonstrates human-level
    understanding across multiple domains.
    """

    try:
        result = analyzer.analyze_content(
            title="AI Breakthrough",
            article_text=test_article,
            source="Test Source"
        )
        print("✅ Analysis succeeded:")
        print(f"   Summary: {result.get('summary', 'N/A')[:100]}...")
        print(f"   Sentiment: {result.get('sentiment', 'N/A')}")

    except PipelineError as e:
        print(f"❌ Fatal error occurred: {e.severity.value}")
        print(f"   Message: {e.message}")
        print(f"   Model: {e.model_name}")

    except Exception as e:
        print(f"⚠️  Unexpected error: {str(e)}")

if __name__ == "__main__":
    asyncio.run(test_article_analysis())
```

#### Execute Test

```bash
python scripts/test_error_handling_integration.py
```

**Expected Outcomes:**
- If API key is valid: Analysis succeeds, returns summary and sentiment
- If API key is invalid: PipelineError with FATAL severity
- If rate limited: Retries with exponential backoff, may succeed or try fallback

### Test 2: Relevance Analysis with Error Handling

Create `scripts/test_relevance_error_handling.py`:

```python
from app.relevance import RelevanceCalculator
from app.exceptions import PipelineError

def test_relevance_analysis():
    """Test relevance analysis with error handling."""

    calculator = RelevanceCalculator(model_name="gpt-4")

    test_article = {
        "title": "Renewable Energy Advances",
        "source": "Tech News",
        "content": "Solar panel efficiency reaches new record high..."
    }

    try:
        result = calculator.analyze_relevance(
            title=test_article["title"],
            source=test_article["source"],
            content=test_article["content"],
            topic="Climate Technology",
            keywords="solar, renewable, energy"
        )

        print("✅ Relevance analysis succeeded:")
        print(f"   Topic Alignment: {result['topic_alignment_score']:.2f}")
        print(f"   Keyword Relevance: {result['keyword_relevance_score']:.2f}")
        print(f"   Confidence: {result['confidence_score']:.2f}")

    except PipelineError as e:
        print(f"❌ Fatal error: {e.severity.value} - {e.message}")

    except Exception as e:
        print(f"⚠️  Error: {str(e)}")

if __name__ == "__main__":
    test_relevance_analysis()
```

#### Execute Test

```bash
python scripts/test_relevance_error_handling.py
```

**Expected Outcomes:**
- Successful analysis returns scores between 0.0 and 1.0
- Errors are properly classified and handled

---

## Circuit Breaker Testing

### Test 3: Circuit Breaker State Transitions

#### Step 1: Reset Circuit Breaker State

```sql
-- Connect to database
PGPASSWORD='<password>' psql -U test_user -d test -h localhost

-- Reset circuit breaker for test model
DELETE FROM llm_retry_state WHERE model_name = 'test-circuit-breaker-model';

-- Verify clean state
SELECT * FROM llm_retry_state WHERE model_name = 'test-circuit-breaker-model';
-- Should return no rows
```

#### Step 2: Create Circuit Breaker Test Script

Create `scripts/test_circuit_breaker_states.py`:

```python
from app.utils.circuit_breaker import CircuitBreaker, CircuitBreakerOpen
from app.database_query_facade import DatabaseQueryFacade
import litellm

def test_circuit_breaker_flow():
    """Test circuit breaker state transitions."""

    cb = CircuitBreaker(model_name="test-circuit-breaker-model")
    db = DatabaseQueryFacade()

    print("1. Initial State (should be CLOSED):")
    state = db.get_llm_retry_state("test-circuit-breaker-model")
    print(f"   Circuit State: {state['circuit_state'] if state else 'NEW'}")
    print(f"   Failures: {state['consecutive_failures'] if state else 0}")

    # Simulate failures
    print("\n2. Recording failures to reach threshold...")
    error = litellm.RateLimitError(
        message="Test error",
        model="test-circuit-breaker-model",
        llm_provider="openai"
    )

    for i in range(5):  # FAILURE_THRESHOLD = 5
        cb.record_failure(error)
        state = db.get_llm_retry_state("test-circuit-breaker-model")
        print(f"   Failure {i+1}: State={state['circuit_state']}, Failures={state['consecutive_failures']}")

    print("\n3. Circuit should now be OPEN:")
    state = db.get_llm_retry_state("test-circuit-breaker-model")
    print(f"   Circuit State: {state['circuit_state']}")

    print("\n4. Attempting request (should be blocked):")
    try:
        cb.check_circuit()
        print("   ❌ Request was allowed (unexpected!)")
    except CircuitBreakerOpen as e:
        print(f"   ✅ Request blocked: {str(e)[:80]}...")

    print("\n5. Recording success to close circuit:")
    cb.record_success()
    state = db.get_llm_retry_state("test-circuit-breaker-model")
    print(f"   Circuit State: {state['circuit_state']}")
    print(f"   Failures: {state['consecutive_failures']}")

    print("\n6. Cleanup:")
    db.reset_llm_retry_state("test-circuit-breaker-model")
    print("   Circuit breaker reset")

if __name__ == "__main__":
    test_circuit_breaker_flow()
```

#### Execute Test

```bash
python scripts/test_circuit_breaker_states.py
```

**Expected Output:**
```
1. Initial State (should be CLOSED):
   Circuit State: closed
   Failures: 0

2. Recording failures to reach threshold...
   Failure 1: State=closed, Failures=1
   Failure 2: State=closed, Failures=2
   Failure 3: State=closed, Failures=3
   Failure 4: State=closed, Failures=4
   Failure 5: State=open, Failures=5

3. Circuit should now be OPEN:
   Circuit State: open

4. Attempting request (should be blocked):
   ✅ Request blocked: Circuit breaker is OPEN for model 'test-circuit-breaker-model'...

5. Recording success to close circuit:
   Circuit State: closed
   Failures: 0

6. Cleanup:
   Circuit breaker reset
```

---

## Relevance Score Persistence Testing

### Test 4: Verify Relevance Scores Are Saved

This test verifies the critical fix for relevance score persistence (Issue #1 and #2 from spec).

#### Step 1: Database Pre-Check

```sql
-- Check recent articles with LLM status
SELECT uri, ingest_status,
       topic_alignment_score,
       keyword_relevance_score,
       confidence_score
FROM articles
WHERE ingest_status IN ('filtered_relevance', 'relevance_check_failed')
ORDER BY created_at DESC
LIMIT 5;
```

#### Step 2: Run Automated Ingest with Monitoring

Create `scripts/test_relevance_score_persistence.py`:

```python
import asyncio
from app.services.automated_ingest_service import AutomatedIngestService
from app.database_query_facade import DatabaseQueryFacade

async def test_score_persistence():
    """Test that relevance scores are persisted correctly."""

    service = AutomatedIngestService()
    db = DatabaseQueryFacade()

    # Test with a low threshold to trigger filtering
    test_uri = "https://example.com/test-article-" + str(int(asyncio.get_event_loop().time()))

    test_article = {
        "uri": test_uri,
        "title": "Unrelated Article About Gardening",
        "source": "Test Source",
        "content": "This article discusses planting tomatoes in spring...",
        "published_at": "2025-01-18T12:00:00Z"
    }

    topic = "Artificial Intelligence"
    keywords = "machine learning, neural networks, AI"

    print(f"Testing relevance score persistence for: {test_uri}")
    print(f"Topic: {topic}")
    print(f"Keywords: {keywords}\n")

    # This should filter the article due to low relevance
    # The fix ensures scores are saved even when filtered

    # Simulate the relevance check (normally done by ingest service)
    from app.relevance import RelevanceCalculator

    try:
        calculator = RelevanceCalculator(model_name="gpt-4")
        result = calculator.analyze_relevance(
            title=test_article["title"],
            source=test_article["source"],
            content=test_article["content"],
            topic=topic,
            keywords=keywords
        )

        print("Relevance Analysis Result:")
        print(f"  Topic Alignment: {result['topic_alignment_score']:.3f}")
        print(f"  Keyword Relevance: {result['keyword_relevance_score']:.3f}")
        print(f"  Confidence: {result['confidence_score']:.3f}")

        # Now check if we can retrieve these from database
        # (In actual implementation, these would be saved by automated_ingest_service)

        # Verify all three scores are present and valid
        assert 'topic_alignment_score' in result
        assert 'keyword_relevance_score' in result
        assert 'confidence_score' in result

        assert 0.0 <= result['topic_alignment_score'] <= 1.0
        assert 0.0 <= result['keyword_relevance_score'] <= 1.0
        assert 0.0 <= result['confidence_score'] <= 1.0

        print("\n✅ All relevance scores are present and valid!")

    except Exception as e:
        print(f"\n❌ Error during relevance check: {str(e)}")

if __name__ == "__main__":
    asyncio.run(test_score_persistence())
```

#### Execute Test

```bash
python scripts/test_relevance_score_persistence.py
```

**Expected Outcomes:**
- All three relevance scores (topic_alignment, keyword_relevance, confidence) are calculated
- Scores are between 0.0 and 1.0
- Low-relevance articles have scores saved before filtering

#### Step 3: Database Verification

```sql
-- Verify scores were saved
SELECT uri, ingest_status,
       topic_alignment_score,
       keyword_relevance_score,
       confidence_score,
       overall_match_explanation
FROM articles
WHERE uri LIKE 'https://example.com/test-article-%'
ORDER BY created_at DESC
LIMIT 3;
```

**Expected Result:**
- All three score columns should have non-NULL values
- `ingest_status` should be 'filtered_relevance' or 'relevance_check_failed'
- Scores should be between 0.0 and 1.0

---

## Error Recovery Testing

### Test 5: Retry with Exponential Backoff

Create `scripts/test_retry_backoff.py`:

```python
import time
from app.utils.retry import retry_sync_with_backoff, RetryConfig
import litellm

def flaky_function(call_count_ref):
    """Simulates a flaky function that fails twice then succeeds."""
    call_count_ref[0] += 1
    print(f"  Attempt {call_count_ref[0]} at {time.time():.2f}")

    if call_count_ref[0] < 3:
        raise litellm.RateLimitError(
            message="Rate limit exceeded",
            model="test-model",
            llm_provider="openai"
        )
    return "Success!"

def test_retry_backoff():
    """Test exponential backoff timing."""

    config = RetryConfig(
        max_attempts=3,
        base_delay=1.0,
        exponential_base=2.0,
        jitter=False  # Disable jitter for predictable timing
    )

    call_count = [0]
    start_time = time.time()

    print("Testing retry with exponential backoff:")
    print(f"Start time: {start_time:.2f}\n")

    result = retry_sync_with_backoff(
        flaky_function,
        call_count,
        retryable_exceptions=(litellm.RateLimitError,),
        config=config
    )

    elapsed = time.time() - start_time

    print(f"\nResult: {result}")
    print(f"Total time: {elapsed:.2f}s")
    print(f"Total attempts: {call_count[0]}")
    print(f"\nExpected delays: 1.0s + 2.0s = 3.0s total")
    print(f"Actual delay: {elapsed:.2f}s")

    # Verify timing (allow some tolerance)
    expected_delay = 3.0  # 1s + 2s
    assert elapsed >= expected_delay - 0.1, "Delays were too short"
    assert elapsed <= expected_delay + 1.0, "Delays were too long"

    print("\n✅ Exponential backoff timing verified!")

if __name__ == "__main__":
    test_retry_backoff()
```

#### Execute Test

```bash
python scripts/test_retry_backoff.py
```

**Expected Output:**
```
Testing retry with exponential backoff:
Start time: 1705582800.00

  Attempt 1 at 1705582800.00
  Attempt 2 at 1705582801.00  # +1.0s
  Attempt 3 at 1705582803.00  # +2.0s

Result: Success!
Total time: 3.01s
Total attempts: 3

Expected delays: 1.0s + 2.0s = 3.0s total
Actual delay: 3.01s

✅ Exponential backoff timing verified!
```

---

## Monitoring and Verification

### Database Monitoring Queries

#### Check Circuit Breaker States

```sql
-- View all circuit breaker states
SELECT model_name,
       circuit_state,
       consecutive_failures,
       last_failure_time,
       last_success_time,
       circuit_opened_at
FROM llm_retry_state
ORDER BY last_updated DESC;
```

#### Check Recent LLM Errors

```sql
-- View recent LLM processing errors
SELECT error_type,
       severity,
       model_name,
       COUNT(*) as error_count,
       MAX(timestamp) as last_occurrence
FROM llm_processing_errors
WHERE timestamp > NOW() - INTERVAL '1 hour'
GROUP BY error_type, severity, model_name
ORDER BY error_count DESC;
```

#### Check Error Rate by Model

```sql
-- Calculate error rate by model
SELECT model_name,
       COUNT(*) as total_errors,
       COUNT(CASE WHEN severity = 'fatal' THEN 1 END) as fatal_errors,
       COUNT(CASE WHEN severity = 'recoverable' THEN 1 END) as recoverable_errors,
       COUNT(CASE WHEN will_retry = true THEN 1 END) as retried_errors
FROM llm_processing_errors
WHERE timestamp > NOW() - INTERVAL '24 hours'
GROUP BY model_name
ORDER BY total_errors DESC;
```

#### Verify Relevance Score Persistence

```sql
-- Check for articles missing relevance scores
SELECT ingest_status,
       COUNT(*) as total,
       COUNT(topic_alignment_score) as with_topic_score,
       COUNT(keyword_relevance_score) as with_keyword_score,
       COUNT(confidence_score) as with_confidence_score
FROM articles
WHERE created_at > NOW() - INTERVAL '24 hours'
  AND ingest_status IN ('filtered_relevance', 'relevance_check_failed', 'processed')
GROUP BY ingest_status;
```

**Expected Result:** All counts should be equal (no missing scores)

---

## Troubleshooting

### Issue: Tests Fail with Database Connection Error

**Symptoms:**
```
psycopg2.OperationalError: could not connect to server
```

**Solution:**
1. Verify PostgreSQL is running: `sudo systemctl status postgresql`
2. Check database credentials in `.env` file
3. Test connection: `PGPASSWORD='<password>' psql -U test_user -d test -h localhost -c "SELECT 1;"`

### Issue: Circuit Breaker Not Opening

**Symptoms:**
- Circuit breaker stays CLOSED despite many failures
- Requests continue even after threshold

**Diagnosis:**
```sql
-- Check circuit breaker state
SELECT * FROM llm_retry_state WHERE model_name = '<your-model>';
```

**Solution:**
1. Verify `FAILURE_THRESHOLD` is set correctly (default: 5)
2. Check that `record_failure()` is being called
3. Verify database updates are succeeding

### Issue: Relevance Scores Not Saved

**Symptoms:**
- Articles have NULL values for relevance scores
- Filtering works but scores are missing

**Diagnosis:**
```sql
-- Find articles with missing scores
SELECT uri, ingest_status,
       topic_alignment_score,
       keyword_relevance_score,
       confidence_score
FROM articles
WHERE ingest_status IN ('filtered_relevance', 'relevance_check_failed')
  AND (topic_alignment_score IS NULL
       OR keyword_relevance_score IS NULL
       OR confidence_score IS NULL)
LIMIT 10;
```

**Solution:**
1. Verify fix #1 is applied (automated_ingest_service.py lines 649-662)
2. Verify fix #2 is applied (automated_ingest_service.py lines 630-637)
3. Check logs for exceptions during relevance check

### Issue: Retries Not Working

**Symptoms:**
- Recoverable errors fail immediately
- No retry delays observed

**Diagnosis:**
- Check logs for "Retrying after" messages
- Verify `retry_sync_with_backoff` is being called

**Solution:**
1. Ensure error is in `RECOVERABLE_EXCEPTIONS` list
2. Verify `RetryConfig` is properly configured
3. Check that `time.sleep()` is not mocked in production

### Issue: Tests Pass but Integration Fails

**Symptoms:**
- Unit tests pass
- Integration with real API fails

**Solution:**
1. Check API key validity
2. Verify model names are correct
3. Check API rate limits haven't been exceeded
4. Review circuit breaker state (might be OPEN)

---

## Test Completion Checklist

Use this checklist to verify all testing is complete:

### Unit Tests
- [ ] Exception classification tests pass (test_exceptions.py)
- [ ] Retry logic tests pass (test_retry.py)
- [ ] Circuit breaker tests pass (test_circuit_breaker.py)
- [ ] AI models error handling tests pass (test_ai_models_error_handling.py)

### Integration Tests
- [ ] Article analysis with error handling works
- [ ] Relevance analysis with error handling works
- [ ] Circuit breaker state transitions work
- [ ] Retry with exponential backoff works

### Database Verification
- [ ] Circuit breaker states are persisted
- [ ] LLM errors are logged correctly
- [ ] Relevance scores are saved (all three fields)
- [ ] Article LLM status is updated

### Error Recovery
- [ ] Fatal errors stop pipeline (no retries)
- [ ] Recoverable errors retry with backoff
- [ ] Skippable errors try fallback (no retries)
- [ ] Degraded errors try fallback

### Monitoring
- [ ] Database queries return expected results
- [ ] Error rates are within acceptable limits
- [ ] Circuit breakers open/close correctly
- [ ] No missing relevance scores in database

---

## Next Steps

After completing manual testing:

1. **Review Test Results**: Document any failures or unexpected behavior
2. **Performance Testing**: Run load tests to verify error handling under load
3. **Production Readiness**: Review all test results with team
4. **Monitoring Setup**: Configure alerts for high error rates and open circuits
5. **Documentation**: Update any findings in ERROR_HANDLING.md

---

## Support

For issues or questions:
- Review implementation spec: `docs/IMPLEMENTATION_SPEC_LLM_ERROR_HANDLING.md`
- Check completion doc: `docs/LLM_ERROR_HANDLING_IMPLEMENTATION_COMPLETE.md`
- Review code comments in modified files
- Check logs: `tail -f /var/log/aunoo/backend.log`

---

**Document Version:** 1.0
**Last Updated:** 2025-01-18
**Status:** Complete
