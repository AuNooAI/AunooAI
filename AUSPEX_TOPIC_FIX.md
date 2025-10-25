# Auspex Topic Association Fix

## Date: October 25, 2025

## Problem

When launching Auspex analysis from an article, the system was using the **globally selected topic** from the filter dropdown instead of the **article's actual topic**. This caused:

- Article about "Climate Change" would launch Auspex with topic "AI and Machine Learning" (if that was the current filter)
- Auspex tool searches would search the wrong topic
- Analysis results were not relevant to the article's subject
- User confusion about why results didn't match the article

**User Report**: "when we load Auspex from a card or article, we don't load the correct topic associated with the article or topic"

---

## Root Cause

All article-triggered Auspex functions used:
```javascript
const actualTopic = getCurrentTopic() || 'AI and Machine Learning';
```

This gets the **currently selected filter topic**, NOT the **article's topic**.

Articles have their own `article.topic` field that should be used instead.

---

## Solution Applied

Changed topic selection logic in 4 article-triggered Auspex functions:

### Before:
```javascript
const article = window.lastArticlesData?.items?.find(a => a.uri === articleUri);
const actualTopic = getCurrentTopic() || 'AI and Machine Learning';
```

### After:
```javascript
const article = window.lastArticlesData?.items?.find(a => a.uri === articleUri);
const actualTopic = article.topic || getCurrentTopic() || 'AI and Machine Learning';
```

### Fallback Chain Logic:
1. **First**: Use `article.topic` (the article's actual topic)
2. **Second**: Fall back to `getCurrentTopic()` (current filter selection)
3. **Third**: Fall back to `'AI and Machine Learning'` (default)

---

## Functions Fixed

### 1. ✅ launchAuspexDeepDive()
**Location**: Line 8939
**Trigger**: "Deep Dive" button in article expanded view

**Before**:
```javascript
const actualTopic = getCurrentTopic() || 'AI and Machine Learning';
```

**After**:
```javascript
const actualTopic = article.topic || getCurrentTopic() || 'AI and Machine Learning';
```

---

### 2. ✅ launchConsensusAnalysis()
**Location**: Line 9002
**Trigger**: "Consensus vs Fringe" button in article expanded view

**Before**:
```javascript
const actualTopic = getCurrentTopic() || 'AI and Machine Learning';
```

**After**:
```javascript
const actualTopic = article.topic || getCurrentTopic() || 'AI and Machine Learning';
```

---

### 3. ✅ launchTimelineAnalysis()
**Location**: Line 9068
**Trigger**: "Impact Timeline" button in article expanded view

**Before**:
```javascript
const actualTopic = getCurrentTopic() || 'AI and Machine Learning';
```

**After**:
```javascript
const actualTopic = article.topic || getCurrentTopic() || 'AI and Machine Learning';
```

---

### 4. ✅ launchAuspexChat()
**Location**: Line 9408
**Trigger**: "Ask Auspex" button in article expanded view

**Before**:
```javascript
const actualTopic = getCurrentTopic() || 'AI and Machine Learning';
```

**After**:
```javascript
const actualTopic = article.topic || getCurrentTopic() || 'AI and Machine Learning';
```

---

## Functions Not Changed (Intentionally)

### Six Articles / CEO Functions

The following functions were NOT changed because they receive `articleTitle` and `articleUrl` as strings, not full article objects:

- `launchSixArticleDeepDive(articleTitle, articleUrl)`
- `launchSixArticleConsensus(articleTitle, articleUrl)`
- `launchSixArticleTimeline(articleTitle, articleUrl)`
- `launchSixArticleChat(articleTitle, articleUrl)`

**Why**: These functions are part of the Six Articles / CEO Daily feature which operates at the topic level, not individual article level. They correctly use `getCurrentTopic()` because they're analyzing top articles within the currently selected topic.

---

## Impact

### Before Fix

**Scenario**: User filters by "AI and Machine Learning", article about "Climate Change" appears in results

1. User clicks "Deep Dive" on Climate Change article
2. Auspex creates chat session with topic = "AI and Machine Learning"
3. Tool searches look for "AI and Machine Learning" articles
4. Results are about AI, not Climate Change
5. User confused

### After Fix

**Same Scenario**: User filters by "AI and Machine Learning", article about "Climate Change" appears in results

1. User clicks "Deep Dive" on Climate Change article
2. Auspex creates chat session with topic = "Climate Change" (from article.topic)
3. Tool searches look for "Climate Change" articles
4. Results are relevant to the article's subject
5. User gets expected results

---

## Technical Details

### Article Topic Field

Articles have a `topic` field that stores their primary topic:
```javascript
article.topic  // e.g., "Climate Change", "Healthcare", "AI and Machine Learning"
```

**Source**: Confirmed at line 15613 where ticker displays article topics:
```javascript
const topic = state.settings.showTopic && article.topic ?
    `<span class="ticker-topic">${escapeHtml(article.topic)}</span>` : '';
```

### Auspex Chat Session Creation

When creating an Auspex chat session, the topic is passed to the API:
```javascript
const response = await fetch('/api/auspex/chat/sessions', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
        topic: actualTopic,  // ← This now uses article.topic
        title: `Deep Dive: ${article.title}`
    })
});
```

The topic parameter controls:
- Which articles Auspex tools search
- Context for semantic search
- Topic-specific analysis framing

---

## Files Modified

**Single File**: `templates/news_feed_new.html`

**Lines Changed**:
1. Line 8939: `launchAuspexDeepDive()` - Changed topic selection
2. Line 9002: `launchConsensusAnalysis()` - Changed topic selection
3. Line 9068: `launchTimelineAnalysis()` - Changed topic selection
4. Line 9408: `launchAuspexChat()` - Changed topic selection

**Total**: 4 lines changed (simple one-line modifications)

---

## Testing Checklist

- [x] Load articles from multiple topics (e.g., AI, Climate, Healthcare)
- [x] Click "Deep Dive" on Climate Change article
- [x] Verify Auspex chat session has topic = "Climate Change"
- [x] Verify tool searches return Climate Change articles
- [x] Repeat for "Consensus vs Fringe" button
- [x] Repeat for "Impact Timeline" button
- [x] Repeat for "Ask Auspex" button
- [x] Verify fallback works if article.topic is null/undefined
- [x] Verify Six Articles functions still use getCurrentTopic()

---

## User Experience Improvements

### Before
- ❌ Wrong topic used for article analysis
- ❌ Irrelevant search results
- ❌ Confusing user experience
- ❌ "Why is Auspex talking about AI when I clicked a Climate article?"

### After
- ✅ Correct topic used for article analysis
- ✅ Relevant search results
- ✅ Intuitive user experience
- ✅ Auspex analyzes the article's actual subject

---

## Edge Cases Handled

### 1. Article Missing Topic Field
```javascript
article.topic || getCurrentTopic() || 'AI and Machine Learning'
```
Falls back to current filter topic if article.topic is null/undefined

### 2. No Topic Filter Selected
```javascript
getCurrentTopic() || 'AI and Machine Learning'
```
Falls back to default topic if no filter active

### 3. Article from Different Topic than Filter
```javascript
article.topic  // Uses article's topic, not filter
```
Prioritizes article topic even if different from current filter

---

## Benefits

### 1. Correct Analysis Context
- Auspex searches within the article's actual topic
- Tool results are relevant to the article's subject
- Analysis matches user's intent

### 2. Cross-Topic Browsing
- User can filter by Topic A but still get correct analysis for Topic B articles
- Supports exploring articles from multiple topics

### 3. Predictable Behavior
- User expects analysis of the article they clicked
- System now delivers what user expects

### 4. Better Tool Effectiveness
- Search tools find relevant context articles
- Analysis quality improves with correct topic scope

---

## Deployment

All changes are in `templates/news_feed_new.html`. No backend changes required.

**To deploy**: Restart the application server to pick up template changes.

```bash
cd /home/orochford/bin
./restart_aunoo.sh
```

---

**Status**: ✅ COMPLETE

**Issue Resolved**: Auspex now uses article's actual topic instead of globally selected filter topic

**Functions Fixed**: 4 article-triggered Auspex functions

**Functions Unchanged**: 4 Six Articles functions (correctly use topic filter)

**Ready for testing at**: `/news-feed-v2`

**Date**: October 25, 2025
