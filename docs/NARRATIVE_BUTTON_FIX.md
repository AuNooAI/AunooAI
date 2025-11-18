# Narrative Explorer Button Color Fix

**Date:** 2025-11-18 16:56:43 CET
**Issue:** Card buttons in Narrative Explorer showing pink text on pink background
**Status:** ✅ **FIXED**

---

## Problem

In the **News Narrator** → **Narrative Explorer** → **Narratives** tab, the "Research with Auspex" buttons on theme cards were displaying with:
- **Pink text** on **Pink/gradient background**
- Text was barely readable/invisible

---

## Root Cause

The `.btn-outline-primary` buttons inside `.insight-item-card` were inheriting the global pink color from the theme:

```css
.btn-outline-primary {
    color: var(--colors-accent-8);  /* Pink text */
    border-color: var(--colors-accent-7);
}
```

When these buttons appeared on cards with pink/gradient backgrounds, the pink text was unreadable.

---

## The Fix

Added specific CSS rules for buttons inside narrative cards to override with white text on solid pink background:

**File:** `templates/news_feed_new.html` (lines 2135-2150)

```css
/* Fix button text color in narrative cards */
.insight-item-card .btn-outline-primary {
    background-color: var(--colors-accent-8);
    border-color: var(--colors-accent-8);
    color: white !important;
}

.insight-item-card .btn-outline-primary:hover {
    background-color: var(--colors-accent-9);
    border-color: var(--colors-accent-9);
    color: white !important;
}

.insight-item-card .btn-outline-primary i {
    color: white !important;
}
```

---

## Changes

### Before (Broken)
- Button text: **Pink** (var(--colors-accent-8))
- Button background: **Transparent/outline**
- On pink card: **Pink on pink = unreadable**

### After (Fixed)
- Button text: **White** (!important override)
- Button background: **Solid pink** (var(--colors-accent-8))
- On any card: **White on pink = readable**
- Hover: **Darker pink** (var(--colors-accent-9))

---

## Affected Components

This fix applies to buttons in:
- **Narrative Explorer** → **Narratives** tab
- Article theme cards
- Research buttons showing "Research with Auspex"

The fix is scoped to `.insight-item-card` containers only, so it won't affect buttons elsewhere in the application.

---

## Testing

1. Go to **News Narrator** (`/news-feed-v2`)
2. Click **Narrative Explorer** tab
3. Click **Narratives** sub-tab
4. Generate insights
5. Verify buttons show **white text on pink background**
6. Hover over buttons - should show **darker pink** background

---

## Files Changed

- `templates/news_feed_new.html` (lines 2135-2150)
  - Added CSS rules for `.insight-item-card .btn-outline-primary`
  - Added hover state styling
  - Added icon color override

---

**Status:** ✅ **DEPLOYED AND READY**

The buttons now have proper contrast with white text on pink background!

---

**Deployment Date:** 2025-11-18 16:56:43 CET
**Service:** Restarted successfully
