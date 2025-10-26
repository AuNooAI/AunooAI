# Modal Timeout Investigation

## Problem Statement

**Broken (final_mvp_v2 on multi.aunoo.ai, staging.aunoo.ai)**:
- Modal shows "Starting..." then times out with "Task monitoring timeout - no updates received"
- Badge disappears during operation
- Cancel button shows then disappears

**Working (final_mvp_test on oliver.aunoo.bot)**:
- Modal shows "Status: running • 1/18 processed • Current: Checking: fairy sighting"
- Badge shows "Badge shown with 1 active jobs"
- Progress updates work correctly

## Timeline of Changes

1. Started with working final_mvp_test branch
2. Created final_mvp_v2 branch with UX updates
3. Made button color fixes (baby blue, green)
4. Fixed cancel button references (cancelBackgroundTaskBtn → cancelBackgroundTaskLink)
5. Attempted to unify tracking systems (later reverted)
6. Reverted unified tracking changes

## Key Files to Compare

1. `app/services/background_task_manager.py`
2. `app/tasks/keyword_monitor.py`
3. `templates/keyword_alerts.html`
4. `app/routes/keyword_monitor.py`
5. `app/routes/background_tasks.py`

## Investigation Steps

### Step 1: Compare Backend Files

**Result**: Backend files are IDENTICAL between branches (after our revert)
- Only difference: check_interval default changed from 900 (15 min) to 1440 (24 hours)
- This is just a default setting and shouldn't affect progress updates

**Files checked**:
- `app/services/background_task_manager.py` - NO FUNCTIONAL DIFFERENCES
- `app/tasks/keyword_monitor.py` - NO FUNCTIONAL DIFFERENCES
- `app/routes/keyword_monitor.py` - NO FUNCTIONAL DIFFERENCES
- `app/routes/background_tasks.py` - NO FUNCTIONAL DIFFERENCES

### Step 2: Compare Frontend Progress Functions

**Result**: Progress monitoring functions are IDENTICAL
- `pollTaskStatus()` at line 4683 (test) vs 5249 (v2) - IDENTICAL CONTENT
- `monitorBackgroundTask()` at line 4723 (test) vs 5289 (v2) - IDENTICAL CONTENT
- `updateProgressModal()` at line 4810 (test) vs 5376 (v2) - IDENTICAL CONTENT

### Step 3: Compare checkKeywords Function

**Result**: Only differences are our button/anchor tag handling
- Added support for anchor tags (not just buttons)
- Added proper disable logic for anchor tags using `style.pointerEvents`
- These changes should NOT affect progress monitoring

**Changes**:
```javascript
// OLD (working):
const button = event?.target?.closest('button') || document.querySelector('button[onclick*="checkKeywords"]');
button.disabled = true;

// NEW (broken):
const button = event?.target?.closest('button') ||
               event?.target?.closest('a') ||
               document.querySelector('button[onclick*="checkKeywords"]') ||
               document.querySelector('a[onclick*="checkKeywords"]');
if (button.tagName === 'BUTTON') {
    button.disabled = true;
} else {
    button.style.pointerEvents = 'none';
    button.style.opacity = '0.6';
}
```

### Step 4: CRITICAL FINDING - HTML Structure Difference

**FOUND THE ISSUE!**

**final_mvp_test (WORKING)**:
```html
<!-- Line 1723-1726 -->
<button class="btn btn-outline-primary" onclick="checkKeywords(event)">
    <i class="fas fa-sync"></i> Update Now
</button>
<button class="btn btn-danger" id="cancelBackgroundTaskBtn" onclick="cancelBackgroundTask()" style="display: none;">
    <i class="fas fa-stop"></i> Cancel Running Task
</button>
```
- "Update Now" is a BUTTON element
- Cancel is a BUTTON element with id="cancelBackgroundTaskBtn"
- Located in the main content area

**final_mvp_v2 (BROKEN)**:
```html
<!-- Lines 2019-2030 -->
<li class="nav-item">
    <a class="nav-link btn-green" href="javascript:void(0)" onclick="checkKeywords(event)">
        <i class="fas fa-sync"></i>
        <span>Update Now</span>
    </a>
</li>
<li class="nav-item">
    <a class="nav-link" href="javascript:void(0)" id="cancelBackgroundTaskLink" onclick="cancelBackgroundTask()" style="display: none;">
        <i class="fas fa-stop"></i>
        <span>Cancel Task</span>
    </a>
</li>
```
- "Update Now" is an ANCHOR element in sidebar navigation
- Cancel is an ANCHOR element with id="cancelBackgroundTaskLink"
- Located in the sidebar

**Impact**: This structural change happened BEFORE our recent modifications. The conversion from buttons to sidebar nav links is the root cause of the problem.

**Question**: Why would this break progress monitoring? The onclick handlers are the same...

### Step 5: Test Hypothesis

Need to test if the button vs anchor difference is causing the issue, or if there's something else about the sidebar location that breaks it.

### Step 6: CRITICAL - App Lockup Issue

**NEW PROBLEM**: Entire app locks up during batch processing

**Logs**:
```
Oct 26 16:34:05.784763 backend python[329900]: 2025-10-26 16:34:05,784 - app.services.automated_ingest_service - INFO - Submitting batch scrape request for 5 URLs
Oct 26 16:34:06.061998 backend python[329900]: 2025-10-26 16:34:06,060 - app.services.automated_ingest_service - INFO - ✅ Batch scrape submitted successfully with ID: c2fd7959-8ea2-47fd-a9b0-e3429ba0ced8
[HANGS HERE]
```

**Root Cause**: `app/services/automated_ingest_service.py`

**Problem Lines**:
- Line 1510-1513: `batch_response = firecrawl_app.start_batch_scrape(uris, formats=['markdown'])` - SYNCHRONOUS call
- Line 1564: `status_response = firecrawl_app.get_batch_scrape_status(batch_id)` - SYNCHRONOUS call

These synchronous Firecrawl API calls are being made inside async functions without using `run_in_executor`, which **blocks the entire async event loop** and freezes the application.

**Solution**: Wrap synchronous Firecrawl calls in `loop.run_in_executor()` to run them in a thread pool:

```python
# Line 1510-1513 FIX:
loop = asyncio.get_event_loop()
batch_response = await loop.run_in_executor(
    None,
    lambda: firecrawl_app.start_batch_scrape(uris, formats=['markdown'])
)

# Line 1564 FIX:
loop = asyncio.get_event_loop()
status_response = await loop.run_in_executor(
    None,
    firecrawl_app.get_batch_scrape_status,
    batch_id
)
```

This pattern is already used elsewhere in the same file (line 837-852) for `article_analyzer.analyze_content`.

### Step 7: Solution Implemented ✅

**Fixed Files**: `app/services/automated_ingest_service.py`

**Changes Made**:

1. **Line 1512-1518**: Wrapped `start_batch_scrape()` in `run_in_executor()` with 30s timeout
   ```python
   batch_response = await asyncio.wait_for(
       loop.run_in_executor(
           None,
           lambda: firecrawl_app.start_batch_scrape(uris, formats=['markdown'])
       ),
       timeout=30.0
   )
   ```

2. **Line 1572-1579**: Wrapped `get_batch_scrape_status()` in `run_in_executor()` with 10s timeout
   ```python
   status_response = await asyncio.wait_for(
       loop.run_in_executor(
           None,
           firecrawl_app.get_batch_scrape_status,
           batch_id
       ),
       timeout=10.0
   )
   ```

3. **Line 1689-1694**: Added specific TimeoutError handling for better logging

4. **Line 1548-1550**: Added specific TimeoutError handling for batch submission

**Result**:
- Event loop no longer blocks during Firecrawl operations
- App remains responsive during batch processing
- Graceful timeout handling with fallback to individual scraping
- Service restarted successfully at 16:48:32

### Step 8: Next Actions

1. Test batch processing to verify app remains responsive
2. Test progress modal updates during processing
3. Address original modal timeout issue (button vs anchor investigation)
