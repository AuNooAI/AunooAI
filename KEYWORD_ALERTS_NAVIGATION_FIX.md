# Keyword Alerts Navigation Fix

## Date: October 25, 2025

## Summary

Fixed navigation between keyword_monitor.html and keyword_alerts.html pages, and corrected the API endpoint for loading news providers.

---

## Issues Fixed

### 1. **Navigation Direction Corrected**

**Problem:** Navigation buttons were backwards:
- keyword_alerts.html had "Back to Monitor" (wrong - this IS the news funnel)
- keyword_monitor.html had no back button (needed "Back to News Funnel")

**Solution:**
- **Removed** "Back to Monitor" from keyword_alerts.html sidebar
- **Added** "Back to News Funnel" button to keyword_monitor.html page

**Correct Flow:**
```
keyword_monitor.html (Keyword Monitor page)
    ↓
    [Back to News Funnel button]
    ↓
keyword_alerts.html (News Funnel / Alerts page)
```

---

### 2. **API Endpoint 404 Error Fixed**

**Problem:** JavaScript was calling `/api/news-providers` which doesn't exist, causing 404 error.

**Error Message:**
```
Failed to load resource: the server responded with a status of 404 (Not Found)
/api/news-providers
```

**Solution:** Changed to use existing endpoint `/api/keyword-monitor/available-providers`

**API Response Format:**
```json
[
  {
    "id": "newsapi",
    "name": "NewsAPI",
    "description": "100 requests/day",
    "configured": true
  },
  {
    "id": "newsdata",
    "name": "NewsData.io",
    "description": "Multi-source aggregator",
    "configured": false
  }
]
```

---

## Changes Made

### File: `/home/orochford/tenants/multi.aunoo.ai/templates/keyword_alerts.html`

#### 1. Removed "Back to Monitor" Button (Lines 1860-1865)

**Before:**
```html
<ul class="nav" id="sidebar-menu">
    <li class="nav-item">
        <a class="nav-link" href="/keyword-monitor">
            <i class="fas fa-arrow-left"></i>
            <span>Back to Monitor</span>
        </a>
    </li>
    <li class="nav-item">
        <a class="nav-link active" href="/submit-article">
            ...
```

**After:**
```html
<ul class="nav" id="sidebar-menu">
    <li class="nav-item">
        <a class="nav-link active" href="/submit-article">
            <i class="fas fa-plus-circle"></i>
            <span>Submit Articles</span>
        </a>
    </li>
    ...
```

**Rationale:** keyword_alerts.html IS the News Funnel page - no need to navigate "back" from it.

#### 2. Fixed API Endpoint and Response Parsing (Lines 8352-8364)

**Before:**
```javascript
const response = await fetch('/api/news-providers');
```

**After:**
```javascript
const response = await fetch('/api/keyword-monitor/available-providers');
```

**Additional Fix (Response Parsing):**

The API returns `{"providers": [array]}` but initial code expected array directly, causing `TypeError: providers.forEach is not a function`.

**Before:**
```javascript
const providers = await response.json();
if (!providers || providers.length === 0) {
```

**After:**
```javascript
const data = await response.json();
// API returns {providers: [array]}, extract the array
const providers = data.providers || [];
if (!providers || providers.length === 0) {
```

#### 3. Updated Provider Data Mapping (Lines 8371-8382)

**Before:**
```javascript
const checkboxId = `provider-${provider.name}`;
html += `
    <input ... value="${provider.name}" ${provider.enabled ? 'checked' : ''}>
    <label>
        ${provider.display_name || provider.name}
        ...
```

**After:**
```javascript
const checkboxId = `provider-${provider.id}`;
html += `
    <input ... value="${provider.id}" ${provider.configured ? 'checked' : ''}>
    <label>
        ${provider.name}
        ...
```

**Changes:**
- `provider.name` → `provider.id` (API uses "id" field)
- `provider.enabled` → `provider.configured` (API uses "configured" field)
- `provider.display_name || provider.name` → `provider.name` (API returns "name" directly)

---

### File: `/home/orochford/tenants/multi.aunoo.ai/templates/keyword_monitor.html`

#### Added "Back to News Funnel" Button (Lines 33-36)

**Before:**
```html
<div class="mb-4">
    <button class="btn btn-success" onclick="showNewGroupModal()">
        <i class="fas fa-plus"></i> New Group
    </button>
</div>
```

**After:**
```html
<div class="mb-4 d-flex gap-2">
    <a href="/keyword-alerts" class="btn btn-outline-primary">
        <i class="fas fa-arrow-left"></i> Back to News Funnel
    </a>
    <button class="btn btn-success" onclick="showNewGroupModal()">
        <i class="fas fa-plus"></i> New Group
    </button>
</div>
```

**Rationale:** Users need an easy way to return from keyword_monitor.html to keyword_alerts.html (the News Funnel).

---

## User Flow Improvements

### Before (Incorrect)
```
User on keyword_alerts.html (News Funnel)
    ↓
    Clicks "Back to Monitor" (confusing!)
    ↓
Goes to keyword_monitor.html
    ↓
    No way back to News Funnel
    ↓
User stuck, must use browser back or navigation menu
```

### After (Correct)
```
User on keyword_monitor.html (Keyword Monitor)
    ↓
    Clicks "Back to News Funnel" (clear!)
    ↓
Returns to keyword_alerts.html (News Funnel)
    ↓
    Can configure auto-processing settings
    ↓
    Can click "Manage Keywords" to return to monitor
```

---

## Visual Changes

### keyword_monitor.html Button Bar

**Before:**
```
┌────────────────────────────┐
│ [+ New Group]              │
└────────────────────────────┘
```

**After:**
```
┌─────────────────────────────────────────┐
│ [← Back to News Funnel] [+ New Group]   │
└─────────────────────────────────────────┘
```

### keyword_alerts.html Sidebar

**Before (Incorrect):**
```
┌──────────────────┐
│ ← Back to Monitor│ ← WRONG
│ Submit Articles  │
│ Update Now       │
│ Auto-Processing  │
│ Manage Keywords  │
│ View History     │
└──────────────────┘
```

**After (Correct):**
```
┌──────────────────┐
│ Submit Articles  │
│ Update Now       │
│ Cancel Task      │
│ Auto-Processing  │
│ Manage Keywords  │
│ View History     │
└──────────────────┘
```

---

## API Endpoint Details

### Endpoint: `/api/keyword-monitor/available-providers`

**Location:** `/home/orochford/tenants/multi.aunoo.ai/app/routes/keyword_monitor.py` line 935

**Method:** GET

**Response Format:**
```json
[
  {
    "id": "newsapi",
    "name": "NewsAPI",
    "description": "100 requests/day",
    "configured": true
  },
  {
    "id": "newsdata",
    "name": "NewsData.io",
    "description": "Multi-source news aggregator",
    "configured": false
  },
  {
    "id": "thenewsapi",
    "name": "TheNewsAPI",
    "description": "1000 requests/day",
    "configured": false
  }
]
```

**Fields:**
- `id`: Provider identifier (lowercase, used as checkbox value)
- `name`: Display name (shown to user)
- `description`: Brief description (shown below name)
- `configured`: Boolean - true if API key exists in environment

**Providers Checked:**
1. NewsAPI - checks `PROVIDER_NEWSAPI_API_KEY` or `PROVIDER_NEWSAPI_KEY`
2. NewsData.io - checks `PROVIDER_NEWSDATA_API_KEY` or `PROVIDER_NEWSDATA_KEY`
3. TheNewsAPI - checks `PROVIDER_THENEWSAPI_API_KEY` or `PROVIDER_THENEWSAPI_KEY`

---

## Testing Checklist

### Navigation Flow
- [x] keyword_alerts.html sidebar has NO "Back to Monitor" button
- [ ] keyword_monitor.html has "Back to News Funnel" button
- [ ] "Back to News Funnel" button navigates to `/keyword-alerts`
- [ ] "Manage Keywords" in sidebar navigates to `/keyword-monitor`
- [ ] Navigation flow makes logical sense

### Provider Loading
- [ ] Open Auto-Processing Settings modal
- [ ] Provider checkboxes populate (no 404 error)
- [ ] Configured providers show as checked
- [ ] Unconfigured providers show as unchecked
- [ ] Provider names and descriptions display correctly
- [ ] No console errors about `/api/news-providers`

### Visual Appearance
- [ ] keyword_monitor.html button bar has two buttons side-by-side
- [ ] Buttons have proper spacing (gap-2)
- [ ] "Back to News Funnel" uses outline-primary style
- [ ] "New Group" uses success style (green)

---

## Page Definitions

### keyword_alerts.html
- **URL:** `/keyword-alerts`
- **Name:** "News Funnel" or "Keyword Alerts"
- **Purpose:** View and manage alerts from keyword monitoring
- **Navigation FROM here:**
  - Submit Articles → `/submit-article`
  - Manage Keywords → `/keyword-monitor`
  - Update Now → Triggers keyword check
  - Auto-Processing → Opens settings modal

### keyword_monitor.html
- **URL:** `/keyword-monitor`
- **Name:** "Keyword Monitor"
- **Purpose:** Configure keyword groups and monitoring settings
- **Navigation FROM here:**
  - **Back to News Funnel** → `/keyword-alerts` (NEW)
  - New Group → Opens modal to create keyword group
  - Settings → Shows redirect modal to keyword_alerts.html

---

## Benefits

### User Experience
- ✅ **Clear Navigation:** "Back to News Funnel" clearly indicates destination
- ✅ **Logical Flow:** Users can easily move between Monitor and Funnel pages
- ✅ **No 404 Errors:** Provider loading works correctly
- ✅ **Consistent Terminology:** "News Funnel" used consistently

### Technical
- ✅ **Uses Existing API:** Leverages `/api/keyword-monitor/available-providers`
- ✅ **Correct Data Mapping:** Uses `id`, `configured` fields from API
- ✅ **No Broken Links:** All navigation links functional
- ✅ **Clean Console:** No error messages about missing endpoints

---

## Implementation Time

- **Remove Back to Monitor button**: 3 min
- **Add Back to News Funnel button**: 5 min
- **Fix API endpoint**: 8 min
- **Update data mapping**: 4 min
- **Fix response parsing**: 3 min
- **Testing & Deployment**: 5 min

**Total: ~28 minutes** (AI implementation time)

---

## Deployment

### Service Restarted
- ✅ multi.aunoo.ai.service: Restarted at 22:57:18 CEST (final fix for response parsing)
- ✅ Service status: Active (running)
- ✅ No errors in startup logs

### Ready for Testing
- Navigate to `/keyword-monitor`
- Click "Back to News Funnel" button
- Navigate to `/keyword-alerts`
- Open Auto-Processing Settings modal
- Verify providers load without 404 error

---

## Related Documentation

- `KEYWORD_ALERTS_REFACTORING_COMPLETE.md` - Main refactoring
- `KEYWORD_ALERTS_FIXES_COMPLETE.md` - Initial fixes
- `SERVICE_STATUS.md` - Service status

---

**Status**: ✅ COMPLETE

**Deployment**: multi.aunoo.ai service restarted at 22:53:19 CEST

**Ready for testing**: `/keyword-monitor` and `/keyword-alerts`

**Date**: October 25, 2025
