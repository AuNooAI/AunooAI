# Article Ingestion Pipeline Analysis

## Current Issues

### 1. **Placeholder Articles Created Without Full Data**
**Location**: `/app/database.py:1713-1715`
```python
INSERT INTO articles (uri, title, news_source, topic, submission_date, analyzed)
VALUES (?, ?, ?, ?, ?, ?)
""", (uri, f"Article from {source}", source, topic, current_time, False))
```
**Problem**: When `save_raw_article()` is called with `create_placeholder=True`, it creates articles with placeholder titles like "Article from medium.com" instead of waiting for the full article data.

**Impact**: Articles show up in the UI with placeholder titles instead of real titles.

### 2. **Badge Color Inconsistency (Yellow vs Blue)**
**Location**: `/templates/keyword_alerts.html:2172`
- Yellow badge: `badge bg-warning` (for "New" articles without enrichment)
- Blue badge: `badge bg-info` (used for status "Processing in progress")

**Problem**: Some "New" articles show yellow badges, others show blue badges. The filtering logic only recognizes yellow badges.

**Root Cause**:
- Yellow: Server-side template checks `if has_enrichment` (line 2167)
- Blue: JavaScript updates based on `ingest_status == 'pending'` (line 2198)

### 3. **Titles Still Missing Despite API Providing Them**
**Root Cause Found**: The `COALESCE` fix I made was WRONG. The actual issue:

1. **Normal flow works correctly**:
   - `create_article()` at line 183 inserts `article['title']` correctly

2. **Placeholder flow breaks it**:
   - `save_raw_article()` creates placeholder: `f"Article from {source}"`
   - Later enrichment update uses `COALESCE(?, title)`
   - If enrichment data doesn't have title, placeholder remains

3. **MY BAD FIX**: Removing COALESCE means if enrichment doesn't have title, it sets title=NULL!

## Complete Ingestion Flow

### Flow A: Keyword Monitor → Normal Insert
```
1. KeywordMonitor.check_keywords()
   ↓
2. collector.search_articles() [Returns articles with 'title']
   ↓
3. create_article() [Inserts with title from API]
   ↓
4. Article saved with CORRECT title ✓
```

### Flow B: Keyword Monitor → Auto-Ingest
```
1. KeywordMonitor.check_keywords()
   ↓
2. collector.search_articles() [Returns articles with 'title']
   ↓
3. auto_ingest_pipeline() [Formats: 'title': article.get('title', '')]
   ↓
4. AutomatedIngestService.process_articles_progressive()
   ↓
5. _process_single_article_async()
   ↓
6. scrape_article_content() [May call save_raw_article()]
   ↓
7. save_raw_article(create_placeholder=True) [Creates "Article from {source}"]
   ↓
8. _analyze_article_content_async() [Enrichment may not include title]
   ↓
9. async_db.update_article_with_enrichment() [Uses COALESCE(?, title)]
   ↓
10. If enrichment has no title → Placeholder remains ✗
11. If enrichment has title → Gets updated ✓
```

### Flow C: Direct save_raw_article Call
```
1. save_raw_article(uri, content, topic, create_placeholder=True)
   ↓
2. Check if article exists
   ↓
3. If NOT exists → INSERT with placeholder title
   ↓
4. Article has "Article from {source}" title ✗
```

## Problems Identified

### Problem 1: Unnecessary Placeholder Creation
**File**: `/app/database.py:1699-1721`
**Issue**: `save_raw_article()` creates placeholder articles when it should fail and let the calling code handle missing articles.

**Current Logic**:
```python
if not existing_article and create_placeholder:
    # Create placeholder
```

**Should Be**:
```python
if not existing_article:
    raise ValueError("Article must be created first with full data")
```

### Problem 2: COALESCE Was Actually Correct, But...
**File**: `/app/services/async_db.py:125`
**Current** (after my edit): `title = ?,`
**Was**: `title = COALESCE(?, title),`

**Issue**: COALESCE was correct, but the enrichment process doesn't include the original title from the API!

**Real Fix Needed**: Ensure enrichment always includes the original title:
```python
enriched_article.update({
    "title": article.get('title'),  # Preserve original title
    "summary": article.get('summary'),  # Preserve original summary
    "category": ...,  # Add enrichment data
    ...
})
```

### Problem 3: Badge Color Logic Split Between Server and Client
**Files**:
- `/templates/keyword_alerts.html:2167-2175` (Server-side)
- `/templates/keyword_alerts.html:4186-4189` (Client-side JavaScript)

**Issue**: Two different systems determining badge color:
1. Server checks `has_enrichment` → Yellow or Green
2. JavaScript checks `ingest_status` → Blue if "pending"

## Proposed Fixes

### Fix 1: Remove Placeholder Article Creation
```python
# In /app/database.py:1699
def save_raw_article(self, uri, raw_markdown, topic, create_placeholder=False):
    # ... existing code ...

    if not existing_article:
        # REMOVED: Placeholder creation
        raise ValueError(f"No article entry found for URI: {uri} - article must be created first")
```

### Fix 2: Preserve Original Data in Enrichment
```python
# In /app/services/automated_ingest_service.py
async def _process_single_article_async(self, article, topic, keywords):
    # Preserve original API data
    enriched_article = {
        **article,  # Start with original article (includes title, summary, etc.)
    }

    # Add enrichment...
    enriched_article.update({
        "category": ...,
        "sentiment": ...,
        # etc.
    })
```

### Fix 3: Restore COALESCE (My Fix Was Wrong)
```python
# In /app/services/async_db.py:125
title = COALESCE(?, title),  # Keep existing if new is NULL
summary = COALESCE(?, summary),
```

### Fix 4: Unify Badge Logic
```python
# Server-side should be the source of truth
# Remove JavaScript badge color changes
# OR: Make JavaScript match server logic exactly

# Standardize:
# - Yellow (bg-warning): category IS NULL or empty → "New"
# - Green (bg-success): category IS NOT NULL → "Added"
# - Blue (bg-info): ONLY for ingest_status='processing' (transient state)
```

### Fix 5: Add Validation
```python
# In create_article()
if not article.get('title') or article['title'].strip() == '':
    raise ValueError(f"Article title required: {article_url}")

# In update_article_with_enrichment()
if article_data.get("title") and article_data["title"].startswith("Article from"):
    logger.warning(f"Placeholder title detected: {article_data['uri']}")
```

### Fix 6: Add Error Checking
```python
# At each step, log what data we have:
logger.info(f"Article data: uri={uri}, has_title={bool(article.get('title'))}, title={article.get('title', '')[:50]}")
```

## Test Plan

### Unit Tests Needed

1. **test_article_creation_with_valid_title**
   - Verify article inserted with API title
   - Assert title != "Article from"

2. **test_article_creation_without_title**
   - Should raise ValueError
   - Should NOT create placeholder

3. **test_enrichment_preserves_title**
   - Create article with title
   - Run enrichment
   - Assert title unchanged

4. **test_badge_color_consistency**
   - Article without enrichment → Yellow
   - Article with enrichment → Green
   - Never Blue unless processing

5. **test_save_raw_article_without_article**
   - Should raise ValueError
   - Should NOT create placeholder

## Implementation Order

1. **Revert my COALESCE change** (back to COALESCE)
2. **Fix enrichment to preserve original title/summary**
3. **Remove placeholder creation** in save_raw_article
4. **Add validation** for empty titles
5. **Unify badge logic**
6. **Add comprehensive logging**
7. **Write tests**
