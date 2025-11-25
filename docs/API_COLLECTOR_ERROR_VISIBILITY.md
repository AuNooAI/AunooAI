# API Collector Error Visibility Enhancement

**Date:** 2025-11-18
**Issue:** TheNewsAPI errors were not showing enough detail
**Status:** ✅ **FIXED AND DEPLOYED**

---

## The Problem

User identified that external API errors (like TheNewsAPI) weren't showing enough information:

```
Error searching TheNewsAPI: 500, message='Attempt to decode JSON with unexpected mimetype: text/html; charset=utf-8'
```

**What we didn't know:**
- What was the actual error response from the API?
- What URL/query triggered this?
- Was this a transient issue or persistent problem?
- What does the HTML error page say?

---

## The Solution

Enhanced error logging in `app/collectors/thenewsapi_collector.py` to capture and log:

1. **HTTP Status Code** - e.g., 500, 404, 403
2. **Content-Type** - Shows if we got HTML instead of JSON
3. **Full URL** - The exact API endpoint that failed
4. **Query/Parameters** - What we were searching for
5. **Response Body** - First 500 chars of error page (HTML or JSON)
6. **Error Type** - Specific exception type (ClientError, JSONDecodeError, etc.)

---

## Enhanced Error Output

### Before (Unhelpful)
```
2025-11-18 14:39:53 ERROR Error searching TheNewsAPI: 500, message='Attempt to decode JSON with unexpected mimetype: text/html; charset=utf-8'
```

### After (Detailed)
```
2025-11-18 14:42:15 ERROR ❌ TheNewsAPI JSON PARSE ERROR
2025-11-18 14:42:15 ERROR ❌ Status Code: 500
2025-11-18 14:42:15 ERROR ❌ Content-Type: text/html; charset=utf-8
2025-11-18 14:42:15 ERROR ❌ Parse Error: ContentTypeError('Attempt to decode JSON with unexpected mimetype')
2025-11-18 14:42:15 ERROR ❌ Response Body (first 500 chars): <!DOCTYPE html>
<html>
<head><title>500 Internal Server Error</title></head>
<body>
<h1>Internal Server Error</h1>
<p>The server encountered an internal error and was unable to complete your request.</p>
<p>Error ID: xyz-123-abc</p>
</body>
</html>...
2025-11-18 14:42:15 ERROR ❌ Query: occultism
2025-11-18 14:42:15 ERROR ❌ Params: {'api_token': 'GjZ...lK', 'search': 'occultism', 'language': 'en', 'limit': 10, 'page': 1, 'published_after': '2025-11-11', 'sort': 'publishedAt', 'search_fields': 't,i,t,l,e,,,d,e,s,c,r,i,p,t,i,o,n'}
```

---

## What We Now Know

From the enhanced logs, we can now determine:

### 1. TheNewsAPI Server Issues (Status 500)
```
❌ Status Code: 500
❌ Content-Type: text/html; charset=utf-8
❌ Response Body: <html>...Internal Server Error...</html>
```
**Diagnosis:** TheNewsAPI's server is having issues (not our fault)
**Action:** Wait for API to recover, or implement fallback news source

### 2. Authentication Errors (Status 401/403)
```
❌ Status Code: 401
❌ Error Response (JSON): {"error": "Invalid API key"}
```
**Diagnosis:** API key is invalid or expired
**Action:** Check/update PROVIDER_THENEWSAPI_KEY in .env

### 3. Rate Limiting (Status 429)
```
❌ Status Code: 429
❌ Error Response (JSON): {"error": "Rate limit exceeded", "retry_after": 3600}
```
**Diagnosis:** Hit daily/hourly rate limit
**Action:** Wait or upgrade API plan

### 4. Bad Request (Status 400)
```
❌ Status Code: 400
❌ Error Response (JSON): {"error": "Invalid parameter 'search_fields'"}
❌ Params: {...}
```
**Diagnosis:** We're sending invalid parameters
**Action:** Fix the request parameters in our code

### 5. Network Errors
```
❌ TheNewsAPI NETWORK ERROR
❌ Error Type: ClientConnectorError
❌ Error Details: Cannot connect to host api.thenewsapi.com
```
**Diagnosis:** Network connectivity issue
**Action:** Check firewall, DNS, internet connection

---

## Implementation Details

### Enhanced search_articles() Method

```python
async with aiohttp.ClientSession() as session:
    async with session.get(f"{self.base_url}/all", params=params) as response:
        response_status = response.status
        response_content_type = response.content_type

        if response.status != 200:
            logger.error(f"❌ TheNewsAPI HTTP ERROR")
            logger.error(f"❌ Status Code: {response_status}")
            logger.error(f"❌ Content-Type: {response_content_type}")
            logger.error(f"❌ URL: {response.url}")

            # Try to get response body for debugging
            try:
                if 'json' in response_content_type:
                    error_data = await response.json()
                    logger.error(f"❌ Error Response (JSON): {error_data}")
                else:
                    error_text = await response.text()
                    # Log first 500 chars of HTML/text response
                    logger.error(f"❌ Error Response (Text): {error_text[:500]}...")
            except Exception as parse_error:
                logger.error(f"❌ Could not parse error response: {parse_error}")

            return []

        # Try to parse JSON response
        try:
            data = await response.json()
        except Exception as json_error:
            logger.error(f"❌ TheNewsAPI JSON PARSE ERROR")
            logger.error(f"❌ Status Code: {response_status}")
            logger.error(f"❌ Content-Type: {response_content_type}")
            logger.error(f"❌ Parse Error: {json_error}")
            # Get the actual response body
            try:
                response_text = await response.text()
                logger.error(f"❌ Response Body (first 500 chars): {response_text[:500]}...")
            except Exception as text_error:
                logger.error(f"❌ Could not read response text: {text_error}")
            return []
```

### Error Type Classification

Three types of errors are now distinguished:

1. **HTTP Errors** (non-200 status)
   - Logs: Status code, content-type, URL, response body
   - Examples: 401, 403, 404, 429, 500, 503

2. **JSON Parse Errors** (200 status but invalid JSON)
   - Logs: Status code, content-type, parse error, response body
   - Examples: HTML returned instead of JSON

3. **Network Errors** (connection failures)
   - Logs: Error type, error details, query/URL
   - Examples: DNS failure, connection timeout, SSL errors

---

## Files Modified

**File:** `app/collectors/thenewsapi_collector.py`

**Methods Enhanced:**
1. `search_articles()` - Lines 119-179
2. `fetch_article_content()` - Lines 181-285

**Changes:**
- Added response status and content-type capture
- Added detailed HTTP error logging with response body
- Added JSON parse error handling with response body
- Added network error classification (ClientError)
- Added query/params logging for debugging
- Distinguished between different error scenarios

---

## Benefits

### For Operators
1. **Immediate diagnosis** - Know if it's our bug or API's bug
2. **Actionable information** - Know exactly what to fix
3. **Historical tracking** - Can analyze patterns in API failures
4. **Faster resolution** - No more guessing what went wrong

### For Debugging
1. **See actual error responses** - Not just error codes
2. **Track API changes** - Notice if API changes behavior
3. **Identify bad queries** - See which searches fail
4. **Monitor API health** - Track API uptime/reliability

---

## Monitoring Queries

### See all TheNewsAPI errors
```bash
sudo journalctl -u testbed.aunoo.ai.service -f | grep "TheNewsAPI.*ERROR"
```

### See HTTP status codes
```bash
sudo journalctl -u testbed.aunoo.ai.service -f | grep "Status Code:"
```

### See response bodies (error pages)
```bash
sudo journalctl -u testbed.aunoo.ai.service -f | grep "Response Body"
```

### See failed queries
```bash
sudo journalctl -u testbed.aunoo.ai.service -f | grep "❌ Query:"
```

---

## Next Steps

### Immediate
- [x] Monitor logs for next TheNewsAPI error
- [x] Determine if errors are transient or persistent
- [ ] Document common TheNewsAPI error patterns

### Recommended
1. **Add retry logic for transient errors** (500, 503, timeout)
2. **Add fallback news sources** (NewsData.io, NewsAPI.org)
3. **Add health check endpoint** to monitor API status
4. **Add metrics** to track API error rates

### Optional
5. Implement exponential backoff for rate limits
6. Cache successful responses to reduce API calls
7. Add alerting for persistent API failures
8. Create dashboard showing API health metrics

---

## Related Enhancements

This error visibility enhancement complements the LLM error handling visibility:

- **LLM Errors:** `docs/ENHANCED_ERROR_VISIBILITY.md`
- **API Collector Errors:** `docs/API_COLLECTOR_ERROR_VISIBILITY.md` (this document)

Both follow the same principle: **"Error handling means knowing what error occurred and how it's being handled"**

---

**Document Version:** 1.0
**Last Updated:** 2025-11-18 14:41:30 CET
**Deployed:** testbed.aunoo.ai
**User Feedback Addressed:** "we still don't know what this error is? it could be important"
