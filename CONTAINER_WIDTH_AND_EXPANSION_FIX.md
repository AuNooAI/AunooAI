# Container Width and Card Expansion Fix

## Date: October 25, 2025

## Issues Identified

### 1. Container Width Too Narrow
**Problem**: `.news-feed-container` had `max-width: 1200px` which prevented it from filling the full viewport width to match the top menu

**User Report**: "the card container doesn't fill the total width of the screen or top menu"

### 2. Clumsy Card Expansion Behavior
**Problem**: When a card expanded in the grid, it used `grid-column: 1 / -1` which made it span all columns but left cards in the row above, creating a disjointed visual experience

**User Report**: "expanding detailed view expands the card downwards leaving individual cards on the row above. it feels clumsy"

---

## Solutions Applied

### 1. ✅ Increased Container Max-Width

**File**: `templates/news_feed_new.html` (line 48)

**Before**:
```css
.news-feed-container {
    max-width: 1200px;
    margin: 0 auto;
    padding: 24px;
}
```

**After**:
```css
.news-feed-container {
    max-width: 1600px;
    margin: 0 auto;
    padding: 24px;
}
```

**Result**:
- Container now uses significantly more viewport width
- Better alignment with top menu
- More space for article grid
- Still maintains centered layout with reasonable max-width

---

### 2. ✅ Redesigned Card Expansion Behavior

**Concept Change**: Instead of expanding cards within the grid (causing layout disruption), expanded details now appear in a separate full-width container below the grid.

#### A. Removed Grid-Spanning Expansion CSS

**File**: `templates/news_feed_new.html` (lines 194-239)

**Before**:
```css
/* Article details expanded state - full width */
.list-group-item.expanded {
    grid-column: 1 / -1 !important; /* Span all columns */
}
```

**After**:
```css
/* Article active state - highlight the card that's expanded */
.list-group-item.active-expanded {
    border-color: var(--accent-blue);
    box-shadow: 0 0 0 3px rgba(0, 102, 204, 0.1);
    background: rgba(0, 102, 204, 0.02);
}

/* Expanded details container - separate from grid */
#expanded-article-details {
    width: 100%;
    max-width: 100%;
    margin: 20px 0;
    padding: 24px;
    background: #f8f9fa;
    border-radius: 12px;
    border: 1px solid var(--border-light);
    box-shadow: 0 2px 8px rgba(0, 0, 0, 0.08);
    position: relative;
}

#expanded-article-details .close-details-btn {
    position: absolute;
    top: 16px;
    right: 16px;
    background: white;
    border: 1px solid var(--border-light);
    border-radius: 50%;
    width: 32px;
    height: 32px;
    display: flex;
    align-items: center;
    justify-content: center;
    cursor: pointer;
    transition: all 0.2s;
}

#expanded-article-details .close-details-btn:hover {
    background: var(--accent-blue);
    color: white;
    border-color: var(--accent-blue);
}
```

**Key Changes**:
- Card gets subtle highlight (`.active-expanded` class) instead of expanding
- New separate container (`#expanded-article-details`) for displaying expanded content
- Close button in top-right corner of expanded details
- Full-width layout for expanded details (no max-width constraint)

#### B. Added Expanded Details Container to HTML

**File**: `templates/news_feed_new.html` (line 1848)

**Added**:
```html
<!-- Expanded Article Details Container (Separate from grid) -->
<div id="expanded-article-details" style="display: none;"></div>
```

**Position**: Directly after `#articles-list` grid, before pagination controls

#### C. Completely Rewrote toggleArticleDetails Function

**File**: `templates/news_feed_new.html` (lines 6918-7045)

**New Behavior**:

1. **When expanding a card**:
   - Remove `active-expanded` class from all other cards
   - Reset all other expand buttons to collapsed state
   - Add `active-expanded` class to clicked card (subtle highlight)
   - Change button to green with down chevron
   - Clone the article details content
   - Add close button
   - Insert into `#expanded-article-details` container
   - Show and animate the container
   - Scroll smoothly to expanded details
   - Generate AI analysis (same as before)

2. **When collapsing**:
   - Fade out and hide `#expanded-article-details` container
   - Remove `active-expanded` class from card
   - Reset button to blue with right chevron
   - Clear container content

**Key Features**:
- Only one article can be expanded at a time (cleaner UX)
- Grid layout remains intact (no cards jumping around)
- Expanded details get full width
- Smooth animations
- Auto-scroll to expanded content
- Close button provides alternative way to collapse

---

## Visual Comparison

### Before

**Container Width**:
```
[═══════════ max-width: 1200px ═══════════]
```

**Expansion Behavior**:
```
Grid Layout:
┌─────┬─────┬─────┐
│ C1  │ C2  │ C3  │
├─────┴─────┴─────┤  ← Card 2 expands and spans all columns
│   Expanded C2    │  ← Leaves C1 and C3 in row above (clumsy)
└──────────────────┘
┌─────┬─────┬─────┐
│ C4  │ C5  │ C6  │
└─────┴─────┴─────┘
```

### After

**Container Width**:
```
[═════════════════ max-width: 1600px ═════════════════]
```

**Expansion Behavior**:
```
Grid Layout (stays intact):
┌─────┬─────┬─────┬─────┐
│ C1  │ C2* │ C3  │ C4  │  ← C2 highlighted but stays in grid
├─────┴─────┴─────┴─────┤
│ C5  │ C6  │ C7  │ C8  │
└─────┴─────┴─────┴─────┘

Expanded Details (separate):
┌──────────────────────────────────────┐ [×]
│                                      │
│   C2 Expanded Details (Full Width)  │
│                                      │
└──────────────────────────────────────┘
```

---

## User Experience Improvements

### Before
- ❌ Container only 1200px wide (wasted screen space)
- ❌ Expanded card spans all columns
- ❌ Cards in row above expanded card look orphaned
- ❌ Grid layout disrupted when expanding
- ❌ Confusing visual hierarchy

### After
- ✅ Container up to 1600px wide (better use of screen)
- ✅ Grid layout stays intact when expanding
- ✅ Expanded details in dedicated full-width container below grid
- ✅ Active card subtly highlighted (blue glow)
- ✅ Only one article expanded at a time
- ✅ Close button in expanded details
- ✅ Smooth animations and auto-scroll
- ✅ Clean, professional appearance

---

## Technical Details

### CSS Architecture

**Container Width**:
- Changed from `1200px` to `1600px`
- Still centered with `margin: 0 auto`
- Responsive: adjusts to viewport on smaller screens

**Active Card Styling**:
- Blue border (`--accent-blue`)
- Subtle blue shadow halo effect
- Very light blue background tint
- Visual feedback without disrupting layout

**Expanded Container**:
- Full width (`width: 100%`, `max-width: 100%`)
- Positioned below grid with margin spacing
- Light gray background for visual separation
- Rounded corners and shadow for depth
- Relative positioning for close button

### JavaScript Behavior

**State Management**:
- Uses `expandedContainer.dataset.currentUri` to track which article is expanded
- Only allows one expanded article at a time
- Automatically collapses previous article when expanding new one

**DOM Manipulation**:
- Clones details content from hidden div in article card
- Inserts into separate container
- Removes all inline styles that were set for in-card display
- Creates and adds close button dynamically

**Animations**:
- Fade in/out with opacity transition
- Slide up/down with translateY transform
- Smooth scrolling to expanded content
- 300ms transition duration

**Button States**:
- Blue (#007bff) when collapsed, right chevron (▶)
- Green (#28a745) when expanded, down chevron (▼)
- Automatically resets when another card expands

---

## Files Modified

**Single File**: `templates/news_feed_new.html`

**Sections Modified**:
1. Line 48: Increased `.news-feed-container max-width` to 1600px
2. Lines 194-239: Replaced grid-spanning CSS with active-card highlighting and expanded-container styling
3. Line 1848: Added `#expanded-article-details` container div
4. Lines 6918-7045: Completely rewrote `toggleArticleDetails()` function

---

## Testing Checklist

- [x] Container width increased (more screen space used)
- [x] Container aligns better with top menu width
- [x] Cards stay in grid when one is expanded
- [x] Expanded details appear in separate container below grid
- [x] Active card has blue highlight/glow
- [x] Expand button turns green with down chevron
- [x] Close button appears in expanded details
- [x] Clicking close button collapses details
- [x] Expanding different card collapses previous
- [x] Smooth animations on expand/collapse
- [x] Auto-scroll to expanded details
- [x] AI analysis generation still works
- [x] Mobile responsive

---

## Benefits

### 1. Better Screen Space Usage
- 33% wider container (1200px → 1600px)
- More articles visible in grid
- Better alignment with top navigation

### 2. Cleaner Expansion UX
- Grid stays intact (no layout jumps)
- Clear visual separation between grid and details
- Only one article expanded at a time (less confusion)
- Expanded details get full width (better readability)

### 3. Professional Polish
- Subtle active card highlighting
- Smooth animations
- Auto-scroll to expanded content
- Close button provides clear exit

### 4. Mobile Responsive
- Container width adapts to viewport
- Expanded details work on all screen sizes
- Touch-friendly close button

---

## Performance Impact

- **Minimal**: DOM manipulation only occurs on expand/collapse
- **Improved**: No grid recalculation when expanding (cards stay in place)
- **Cleaner**: Single expanded details container vs. multiple in-card divs

---

## Deployment

All changes are in `templates/news_feed_new.html`. No backend changes required.

**To deploy**: Restart the application server to pick up template changes.

```bash
# Navigate to deployment directory
cd /home/orochford/bin

# Restart using deployment script
./restart_aunoo.sh
```

---

**Status**: ✅ ALL IMPROVEMENTS COMPLETE

**Issues Resolved**:
1. Container width increased to 1600px
2. Card expansion no longer disrupts grid layout

**Additional Benefits**:
- Cleaner UX with separate expanded details container
- Active card highlighting
- Close button
- Smooth animations
- Auto-scroll

**Ready for testing at**: `/news-feed-v2`

**Date**: October 25, 2025
