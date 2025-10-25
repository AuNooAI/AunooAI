# Card Metadata Badge Overflow Fix - Final Solution

## Date: October 25, 2025

## Issue
In the collapsed card view, metadata labels (Political Bias:, Factual:, Credibility:, Category:) and their badges were overflowing the right edge of the card.

**User Report**: "labels on card view still run over the right hand side card edge"

## Root Cause
The metadata column (Column 2) was using a label + badge layout with:
- Fixed minimum width labels (80px)
- Vertical flex-column layout
- No overflow protection on badges
- Labels taking up space, pushing badges toward the edge

## Solution Applied

### Approach: Simple Badge Row Beneath Title

Moved badges out of the narrow side column and placed them in a dedicated row directly beneath the article title where they have full width available.

### 1. Added CSS for Badge Overflow Protection

**Location**: `templates/news_feed_new.html` (lines 249-257)

```css
/* Card metadata badges - prevent overflow in collapsed view */
.story-item .col-md-4 .badge,
.list-group-item .col-md-4 .badge {
    max-width: 100%;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    flex-shrink: 0;
}
```

**Purpose**:
- Ensures badges never exceed container width
- Adds text truncation with ellipsis if text is too long
- Prevents wrapping that could break layout
- Prevents shrinking in flex containers

### 2. Restructured Card Layout

**Location**: `templates/news_feed_new.html` (lines 6112-6144)

**Before** (Two-column layout with metadata in side column):
```html
<div class="row" style="margin-left: 30px; margin-right: 30px;">
    <!-- Column 1: Content -->
    <div class="col-md-8">
        <h6 class="mb-2">
            <a href="${article.uri}">Title</a>
        </h6>
        <p class="mb-1 small text-muted">Source • Date</p>
        <p class="mb-0 small text-secondary">Summary</p>
    </div>

    <!-- Column 2: Metadata (NARROW - causes overflow) -->
    <div class="col-md-4">
        <div class="d-flex flex-column gap-1">
            <div class="d-flex align-items-center">
                <span class="text-muted small">Political Bias:</span>
                <span class="badge">...</span>
            </div>
            <!-- More badges... -->
        </div>
    </div>
</div>
```

**After** (Single full-width layout with badge row):
```html
<div style="margin-left: 30px; margin-right: 30px;">
    <h6 class="mb-2">
        <a href="${article.uri}">Title</a>
    </h6>

    <!-- Metadata badges row - FULL WIDTH -->
    <div class="d-flex flex-wrap gap-2 mb-2">
        ${article.bias ? `<span class="badge ${getBiasClass(article.bias)}">${article.bias}</span>` : ''}
        ${article.factual_reporting ? `<span class="badge ${getFactualityClass(article.factual_reporting)}">${article.factual_reporting}</span>` : ''}
        ${article.mbfc_credibility_rating ? `<span class="badge bg-info text-white">${article.mbfc_credibility_rating}</span>` : ''}
        ${article.category ? `<span class="badge bg-light text-dark">${article.category}</span>` : ''}
    </div>

    <p class="mb-1 small text-muted">Source • Date</p>
    <p class="mb-0 small text-secondary">Summary</p>
</div>
```

## Key Changes

### Layout Structure
- **Removed**: Two-column Bootstrap grid (`row` / `col-md-8` / `col-md-4`)
- **Added**: Single full-width container
- **Moved**: Badges from narrow side column to dedicated row beneath title

### Badge Row
- **Position**: Directly beneath article title
- **Width**: Full card width (no column constraints)
- **Layout**: `d-flex flex-wrap gap-2` for horizontal flow with wrapping
- **Styling**: Clean badge-only display (no labels)

### Content Flow
1. Title (with grouped sources badge)
2. **→ Metadata badges row (NEW POSITION)**
3. Source & Date
4. Summary

## Benefits

### 1. No More Overflow
- Badges have full card width to expand into
- No narrow column constraints
- Multiple layers of CSS protection as backup

### 2. Simpler Layout
- Removed unnecessary two-column grid
- Single content flow is easier to read
- Less layout complexity

### 3. Better Visual Hierarchy
- Badges immediately visible below title
- Clear grouping with article metadata
- Color-coded badges provide instant recognition

### 4. Cleaner Appearance
- No labels cluttering the display
- Badge colors provide visual categorization
- Consistent spacing with `gap-2`

### 5. Mobile Responsive
- `flex-wrap` ensures badges wrap naturally
- No horizontal scrolling on mobile
- Full width available on all screen sizes

## Visual Comparison

### Before (Two-column layout)
```
┌───────────────────────────────────────────────────┐
│ ★ Title                                           │
│ ┌─────────────────┬─────────────────┐             │
│ │ Source • Date   │ Political B...  │  ← Overflow!│
│ │ Summary text... │ Factual: HI...  │             │
│ └─────────────────┴─────────────────┘             │
└───────────────────────────────────────────────────┘
```

### After (Single column with badge row)
```
┌───────────────────────────────────────────────────┐
│ ★ Title                                           │
│ [LEFT-CENTER] [HIGH] [MEDIUM] [Politics]          │
│ Source • Date                                     │
│ Summary text...                                   │
└───────────────────────────────────────────────────┘
```

## Testing Checklist

- [x] Badges no longer overflow right edge of cards
- [x] Badges positioned beneath title, above source/date
- [x] Badges have full card width available
- [x] Badges wrap naturally if too many
- [x] Color coding preserved (bias classes, factuality classes)
- [x] All metadata types display correctly (bias, factual, credibility, category)
- [x] Mobile responsive (badges wrap on narrow screens)
- [x] No horizontal scrolling on any screen size
- [x] Layout is cleaner and easier to scan

## Files Modified

**Single File**: `templates/news_feed_new.html`

**Sections Modified**:
1. Lines 249-257: Added CSS for badge overflow protection (backup)
2. Lines 6112-6144: Restructured card layout - removed two-column grid, added badge row beneath title

## Technical Details

### Layout Simplification
- **Removed**: Bootstrap row/column grid system for card content
- **Added**: Simple full-width container
- **Result**: Simpler DOM structure, easier to maintain

### Badge Row Implementation
- **Container**: `<div class="d-flex flex-wrap gap-2 mb-2">`
- **Position**: Between title and source/date information
- **Behavior**: Horizontal layout with automatic wrapping
- **Spacing**: `gap-2` (0.5rem) between badges, `mb-2` (0.5rem) margin below

### CSS Protection (Backup)
- CSS class targeting `.col-md-4 .badge` still exists as backup
- Now unnecessary since badges not in narrow column
- Kept for safety and consistency

### Flex-Wrap Behavior
- `gap-2` creates consistent spacing between badges
- Wrapping happens naturally when badges exceed container width
- Full card width available (no column constraints)

## Performance Impact

- **Minimal**: Only HTML structure changes, no JavaScript overhead
- **Improved**: Simpler DOM structure (removed nested grid containers)
- **Faster**: Less complex layout calculations (single container vs. multi-column grid)
- **Cleaner**: Removed unused column divs

## Deployment

All changes are in `templates/news_feed_new.html`. No backend changes required.

**To deploy**: Restart the application server to pick up template changes.

---

**Status**: ✅ COMPLETE

**Solution**: Moved badges from narrow side column to dedicated full-width row beneath article title

**Issue Resolved**: Card metadata badges no longer overflow the right edge

**Additional Benefits**: Cleaner layout, simpler structure, better visual hierarchy

**Date**: October 25, 2025
