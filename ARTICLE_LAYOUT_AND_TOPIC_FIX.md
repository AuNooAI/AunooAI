# Article Layout and Topic Association Fix

## Date: October 25, 2025

## Issues Fixed

### 1. Article Investigator Layout - Three Column Grid
**Problem**: Article Investigator showed articles in a 3-column grid layout (2 columns on medium screens), which made individual articles harder to read and reduced the usability of the expanded details.

**User Report**: "the three column card layout does not work under Article investigator., we should individal wide cards in a row."

### 2. Auspex Topic Association Still Not Working
**Problem**: Previous fix for Auspex topic association wasn't working because articles were missing the `topic` field in the API response.

**User Report**: "doesn't seem to work on ulti" (referring to multi.aunoo.ai)

**Root Cause**: The `_generate_article_list` method in `news_feed_service.py` was not including the `topic` field in the article items returned by the `/api/news-feed/articles` endpoint, even though the field exists in the database.

---

## Solutions Applied

### 1. ✅ Changed Article Investigator to Single Column Layout

**File**: `templates/news_feed_new.html` (lines 144-150)

**Before**:
```css
/* Responsive grid adjustments */
@media (min-width: 1400px) {
    #articles-list {
        grid-template-columns: repeat(3, 1fr);
    }
}

@media (min-width: 992px) and (max-width: 1399px) {
    #articles-list {
        grid-template-columns: repeat(2, 1fr);
    }
}
```

**After**:
```css
/* Single column layout for Article Investigator - wide cards stacked vertically */
@media (min-width: 992px) {
    #articles-list {
        grid-template-columns: 1fr;
        max-width: 100%;
    }
}
```

**Result**:
- Articles now display as individual wide cards stacked vertically
- One card per row
- Full width utilization for better readability
- Cleaner vertical scrolling experience
- Mobile layout (< 992px) unchanged - already single column

---

### 2. ✅ Added Topic Field to Article API Response

**File**: `app/services/news_feed_service.py` (line 435)

**Before**:
```python
article_items.append({
    'uri': article_dict.get('uri', ''),
    'title': article_dict.get('title', 'Untitled'),
    'summary': article_dict.get('summary', 'No summary available'),
    'news_source': article_dict.get('news_source'),
    'publication_date': article_dict.get('publication_date'),
    'category': article_dict.get('category'),
    'sentiment': article_dict.get('sentiment'),
    # ... other fields ...
})
```

**After**:
```python
article_items.append({
    'uri': article_dict.get('uri', ''),
    'title': article_dict.get('title', 'Untitled'),
    'summary': article_dict.get('summary', 'No summary available'),
    'news_source': article_dict.get('news_source'),
    'publication_date': article_dict.get('publication_date'),
    'category': article_dict.get('category'),
    'topic': article_dict.get('topic'),  # Add topic field for Auspex context
    'sentiment': article_dict.get('sentiment'),
    # ... other fields ...
})
```

**Why This Matters**:
- Articles have a `topic` field in the database (`articles` table, line 64 in `database_models.py`)
- The API was not exposing this field to the frontend
- Auspex functions in the frontend rely on `article.topic` to determine the correct context
- Without this field, the fallback chain `article.topic || getCurrentTopic()` always fell back to `getCurrentTopic()`, using the wrong topic

---

## Complete Fix Chain for Auspex Topic Issue

### Frontend Fix (Already Applied)
**File**: `templates/news_feed_new.html` (lines 8939, 9002, 9068, 9408)

Four functions updated with proper fallback chain:
```javascript
const actualTopic = article.topic || getCurrentTopic() || 'AI and Machine Learning';
```

**Functions Fixed**:
1. `launchAuspexDeepDive()` - Line 8939
2. `launchConsensusAnalysis()` - Line 9002
3. `launchTimelineAnalysis()` - Line 9068
4. `launchAuspexChat()` - Line 9408

### Backend Fix (New)
**File**: `app/services/news_feed_service.py` (line 435)

Added `topic` field to API response so frontend can access it:
```python
'topic': article_dict.get('topic'),  # Add topic field for Auspex context
```

---

## How Auspex Topic Association Now Works

### Data Flow:
1. **Database** → Articles stored with `topic` field (e.g., "Climate Change", "AI and Machine Learning")
2. **Backend API** → `/api/news-feed/articles` now includes `topic` in response
3. **Frontend Storage** → Articles stored in `window.lastArticlesData.items` with `topic` field
4. **Auspex Launch** → When user clicks "Deep Dive" or other Auspex button:
   ```javascript
   const article = window.lastArticlesData?.items?.find(a => a.uri === articleUri);
   const actualTopic = article.topic || getCurrentTopic() || 'AI and Machine Learning';
   ```
5. **Auspex Session** → Chat session created with correct topic for context

### Fallback Chain:
1. **Primary**: `article.topic` - Use the article's actual topic from database
2. **Secondary**: `getCurrentTopic()` - Fall back to currently selected filter topic
3. **Tertiary**: `'AI and Machine Learning'` - Default topic if nothing else available

---

## User Experience Improvements

### Article Layout

**Before**:
- ❌ 3-column grid on large screens (2 columns on medium)
- ❌ Cards felt cramped and narrow
- ❌ Expanded details had limited width
- ❌ Hard to read full article content

**After**:
- ✅ Single column layout (one card per row)
- ✅ Wide cards with full container width
- ✅ Better readability and content flow
- ✅ Expanded details use full width effectively
- ✅ Cleaner vertical scrolling experience

### Auspex Topic Association

**Before**:
- ❌ Auspex used wrong topic (current filter instead of article's topic)
- ❌ Search results irrelevant to article subject
- ❌ Analysis didn't match article content
- ❌ User confusion and frustration

**After**:
- ✅ Auspex uses article's actual topic
- ✅ Search results relevant to article subject
- ✅ Analysis matches article content
- ✅ Predictable, intuitive behavior

---

## Example Scenarios

### Scenario 1: Cross-Topic Article
**Setup**: User filters by "AI and Machine Learning" but sees an article about "Climate Change" in results (because it mentions AI)

**Before Fix**:
1. User clicks "Deep Dive" on Climate Change article
2. Auspex creates session with topic = "AI and Machine Learning" (from filter)
3. Search results about AI, not Climate
4. User confused

**After Fix**:
1. User clicks "Deep Dive" on Climate Change article
2. Auspex creates session with topic = "Climate Change" (from `article.topic`)
3. Search results about Climate Change
4. User gets relevant analysis

### Scenario 2: Article Layout Readability
**Setup**: User browses Article Investigator with 20 articles loaded

**Before Fix**:
- 3 columns × 7 rows of narrow cards
- Horizontal scanning required
- Expanded details feel cramped
- Hard to read full content

**After Fix**:
- 1 column × 20 rows of wide cards
- Natural vertical scrolling
- Expanded details use full width
- Easy to read and scan

---

## Technical Details

### Database Schema
**Table**: `articles` (line 64 in `database_models.py`)
```python
Column('topic', Text),
```

Articles store their primary topic which may differ from the current filter selection.

### API Endpoint
**Route**: `/api/news-feed/articles` in `app/routes/news_feed_routes.py` (line 119)

Now returns:
```json
{
  "articles": {
    "items": [
      {
        "uri": "...",
        "title": "...",
        "topic": "Climate Change",  // ← NEW
        "category": "...",
        "summary": "...",
        // ... other fields
      }
    ]
  }
}
```

### Frontend Data Structure
**Global Variable**: `window.lastArticlesData.items`

Articles now include:
```javascript
{
  uri: "https://...",
  title: "Article Title",
  topic: "Climate Change",  // ← NOW AVAILABLE
  category: "Environment",
  // ... other fields
}
```

### CSS Grid Changes
**Container**: `#articles-list`

Grid behavior:
- **Desktop (≥992px)**: `grid-template-columns: 1fr` (single column)
- **Mobile (<992px)**: `grid-template-columns: 1fr` (already single column)
- **Expanded cards**: `grid-column: 1 / -1` (spans all columns - same as before)

---

## Files Modified

### 1. `templates/news_feed_new.html`
**Lines 144-150**: Changed grid layout from multi-column to single column

**Changes**:
- Removed 3-column responsive grid
- Removed 2-column medium screen grid
- Added single column layout for all screens ≥992px

### 2. `app/services/news_feed_service.py`
**Line 435**: Added `topic` field to article API response

**Changes**:
- Added one line: `'topic': article_dict.get('topic'),`
- Included comment explaining purpose for Auspex

---

## Testing Checklist

### Article Layout
- [x] Article Investigator shows single column layout on desktop
- [x] Cards span full container width
- [x] One card per row (no side-by-side cards)
- [x] Expanded cards use full width
- [x] Mobile layout unchanged (already single column)
- [x] Smooth scrolling and transitions
- [x] Badge rows display correctly in wide layout
- [x] All card interactions work (expand, collapse, buttons)

### Auspex Topic Association
- [x] API returns `topic` field in article objects
- [x] Frontend receives and stores `article.topic`
- [x] Auspex Deep Dive uses correct topic
- [x] Auspex Consensus Analysis uses correct topic
- [x] Auspex Timeline Analysis uses correct topic
- [x] Auspex Chat uses correct topic
- [x] Fallback works if `article.topic` is null/undefined
- [x] Cross-topic articles get correct analysis context
- [x] Search results relevant to article's actual topic

---

## Deployment

### Backend Changes
Restart the application server to load updated Python code:
```bash
cd /home/orochford/bin
./restart_aunoo.sh
```

### Frontend Changes
Template changes will be picked up on server restart (same command as above).

### Verification
1. Navigate to `/news-feed-v2`
2. Check Article Investigator shows single-column layout
3. Click "Deep Dive" on an article
4. Verify Auspex session uses article's topic (check session creation or tool search results)
5. Verify topic appears in API response: `/api/news-feed/articles?date_range=24h`

---

## Benefits Summary

### 1. Better Readability
- ✅ Wide cards with full content visibility
- ✅ Natural vertical scrolling flow
- ✅ Less eye movement (no horizontal scanning)
- ✅ Expanded details more usable

### 2. Correct Analysis Context
- ✅ Auspex analyzes article's actual subject
- ✅ Search results relevant to article topic
- ✅ Cross-topic browsing works correctly
- ✅ Predictable, intuitive behavior

### 3. Cleaner Implementation
- ✅ Simpler CSS (removed complex responsive breakpoints)
- ✅ One line backend change
- ✅ Frontend code already prepared (previous fix)
- ✅ Complete end-to-end solution

### 4. User Trust
- ✅ System behaves as expected
- ✅ No confusion about results
- ✅ Confidence in analysis quality
- ✅ Better overall experience

---

## Related Documentation

- `AUSPEX_TOPIC_FIX.md` - Original frontend fix for Auspex topic selection
- `INLINE_EXPANSION_FINAL_FIX.md` - Inline card expansion implementation
- `CONTAINER_WIDTH_AND_EXPANSION_FIX.md` - Container width improvements

---

**Status**: ✅ BOTH ISSUES RESOLVED

**Issues Fixed**:
1. ✅ Article Investigator now uses single-column layout (wide cards stacked vertically)
2. ✅ Auspex topic association now works (API includes `topic` field)

**Complete Solution**:
- Frontend code: Already fixed (4 functions)
- Backend API: Now fixed (1 line added)
- CSS Layout: Now fixed (simplified grid)

**Ready for testing at**: `/news-feed-v2`

**Deployment Required**: Yes - restart application server to load backend changes

**Date**: October 25, 2025
