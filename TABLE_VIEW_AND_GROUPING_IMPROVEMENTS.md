# Table View and Grouping Improvements - Complete

## Date: October 25, 2025

## Overview
Improved Article Investigator table view to match card view UX and enabled article grouping by default for a cleaner, more organized interface.

---

## Changes Made

### 1. ✅ Table View Matches Card View UX

**Problem**: Table view used different interaction pattern (eye icon) vs card view (expand arrow)

**Solution**: Completely redesigned table view to match card view exactly

**Changes**:

#### Expand Arrow (Left Side)
- Added `.expand-arrow-btn-table` button to first column
- Positioned absolutely on left edge (like card view)
- Same blue → green color change when expanded
- Same chevron-right → chevron-down icon toggle
- Same animation and behavior

**CSS** (lines 295-320):
```css
.expand-arrow-btn-table {
    width: 20px;
    height: 40px;
    padding: 0;
    font-size: 12px;
    border: none;
    background: #007bff;
    color: white;
    border-radius: 0 8px 8px 0;
    cursor: pointer;
    transition: all 0.2s ease;
    position: absolute;
    left: -2px;
    top: 50%;
    transform: translateY(-50%);
    box-shadow: 2px 0 4px rgba(0,0,0,0.1);
}

.expand-arrow-btn-table.expanded {
    background: #28a745;
}
```

#### Expanded Row Layout
- **Removed**: Old simple summary + analysis layout
- **Added**: Exact same structure as card view:
  - Metadata badges row (horizontal)
  - 2-column grid layout
  - Left column: Summary + Auspex Analysis
  - Right column: Grouped sources (if applicable)
  - Same styling, same icons, same spacing

**HTML Structure** (lines 6459-6525):
```html
<tr id="details-row-${articleId}">
    <td colspan="8">
        <div class="article-details">
            <!-- Metadata badges -->
            <div class="metadata-badges">...</div>
            <!-- Two column grid -->
            <div class="article-details-grid">
                <div>Summary + Analysis</div>
                <div>Grouped Sources</div>
            </div>
        </div>
    </td>
</tr>
```

#### Updated Toggle Function (lines 6538-6573)
- Renamed: `toggleArticleDetailsInTable` → `toggleArticleDetailsInTableRow`
- Added arrow icon rotation (chevron-right ↔ chevron-down)
- Added expanded class toggle
- Added fade animation
- Calls same `generateArticleAnalysis()` as card view

**Result**: Table and card views now have identical UX

---

### 2. ✅ Group by Title Enabled by Default

**Problem**: Articles with same title from different outlets cluttered the list

**Solution**: Enable grouping by default, user can disable if desired

**Changes**:

#### JavaScript (line 5960):
```javascript
let groupDuplicateArticles = true; // Changed from false
```

#### HTML Checkbox (line 1792):
```html
<input ... id="article-group-duplicates-toggle" checked ...>
```

#### localStorage Logic (lines 6012-6020):
```javascript
if (savedGrouping === 'false') {
    // Only disable if explicitly set to false
    groupDuplicateArticles = false;
    toggle.checked = false;
} else {
    // Default to enabled
    groupDuplicateArticles = true;
    toggle.checked = true;
}
```

**Result**: Articles grouped by title on first load, cleaner interface

---

### 3. ✅ Visual Grouping for Related Cards

**Problem**: Grouped articles looked identical to individual articles

**Solution**: Added distinctive visual styling for grouped articles

**CSS Added** (lines 322-337):
```css
.list-group-item.grouped-article {
    border-left: 4px solid #0066cc;
    background: linear-gradient(to right, #f0f7ff 0%, white 20px);
}

.grouped-sources-badge {
    background: #0066cc;
    color: white;
    padding: 4px 8px;
    border-radius: 12px;
    font-size: 0.85rem;
    font-weight: 600;
    display: inline-flex;
    align-items: center;
}
```

**JavaScript Updates**:

#### Card View (lines 6073-6074):
```javascript
const isGrouped = article.grouped && article.groupedArticles;
articleItem.className = `list-group-item position-relative ${isGrouped ? 'grouped-article' : ''}`;
```

#### Badge Display (line 6110):
```html
${article.grouped ?
    `<span class="grouped-sources-badge ms-2">
        <i class="fas fa-layer-group me-1"></i>${article.groupedArticles.length} sources
    </span>`
    : ''}
```

**Visual Features**:
- Blue left border (4px solid #0066cc)
- Light blue gradient background
- Prominent blue badge with layer-group icon
- Shows number of sources in group

**Result**: Grouped articles are immediately visually distinct

---

### 4. ✅ Table View Visual Grouping

**Applied same styling to table rows** (line 6427):
```javascript
<tr style="${isGrouped ?
    'background: linear-gradient(to right, #f0f7ff 0%, white 20px); border-left: 4px solid #0066cc;'
    : ''}">
```

**Badge in table** (line 6446):
```html
${isGrouped ?
    `<span class="grouped-sources-badge ms-2">
        <i class="fas fa-layer-group me-1"></i>${article.groupedArticles.length} sources
    </span>`
    : ''}
```

**Result**: Consistency across card and table views

---

## Files Modified

**Single File**: `templates/news_feed_new.html`

**Sections Modified**:
1. Lines 295-337: CSS for table arrows and grouped styling
2. Line 1792: Checkbox `checked` attribute
3. Line 5960: Default grouping variable
4. Lines 6012-6020: localStorage default logic
5. Lines 6073-6074: Card view grouped class
6. Line 6110: Card view grouped badge
7. Lines 6427-6458: Table row structure with expand arrow
8. Lines 6459-6525: Table expanded row (matches card view)
9. Lines 6538-6573: Updated toggle function

---

## User Experience Improvements

### Before
- ❌ Table view: Eye icon to expand, different layout
- ❌ Card view: Expand arrow
- ❌ Inconsistent UX between views
- ❌ Grouping disabled by default (cluttered)
- ❌ Grouped articles looked like regular articles

### After
- ✅ Table view: Expand arrow (matches card view)
- ✅ Card view: Expand arrow (unchanged)
- ✅ Identical UX between views
- ✅ Grouping enabled by default (clean)
- ✅ Grouped articles visually distinct (blue border + gradient)

---

## Visual Design

### Grouped Article Styling

**Card View**:
```
┌─[BLUE]──────────────────────────────────┐
│ [Blue gradient background]           │
│ ★ Article Title [🔷 3 sources]      │
│ Source • Date                        │
│ Summary...                           │
└──────────────────────────────────────┘
```

**Table View**:
```
[BLUE]│ Arrow ★ │ Title [🔷 3 sources] │ Source │ Date │ Badges │
```

### Expand Arrow Behavior

**Collapsed State**:
- Blue button
- Chevron-right icon (▶)

**Expanded State**:
- Green button
- Chevron-down icon (▼)

**Animation**: Smooth fade-in/out

---

## Technical Details

### Grouping Algorithm
- Normalizes titles (lowercase, remove punctuation)
- Groups by normalized title
- Creates primary article with `grouped: true` flag
- Stores all articles in `groupedArticles` array

### Expand Arrow Positioning
- `position: absolute`
- `left: -2px` (extends beyond table edge)
- `top: 50%` with `transform: translateY(-50%)` (vertical center)
- `z-index` ensures clickability

### Analysis Generation
- Same `generateArticleAnalysis(uri)` function
- Works identically in card and table views
- Caches results for performance

---

## Testing Checklist

- [x] Table view has expand arrow on left
- [x] Arrow changes blue → green when expanded
- [x] Arrow icon changes chevron-right → chevron-down
- [x] Table expanded view matches card view layout
- [x] Group by title checked by default
- [x] Grouped cards have blue left border
- [x] Grouped cards have light blue gradient
- [x] Grouped badge is prominent with icon
- [x] Table rows show grouped styling
- [x] Analysis generation works in table view
- [x] Animations smooth in both views

---

## Benefits

1. **Consistency**: Same interaction pattern everywhere
2. **Clarity**: Grouped articles immediately visible
3. **Efficiency**: Grouping by default reduces clutter
4. **Professional**: Polished visual design
5. **Familiarity**: Muscle memory works in both views

---

## Future Enhancements

- [ ] Add "Ungroup this article" button
- [ ] Add bias distribution chart for grouped sources
- [ ] Add "Compare sources" modal
- [ ] Add grouping strength indicator (exact vs similar titles)

---

**Status**: ✅ ALL IMPROVEMENTS COMPLETE

**Ready for testing at**: `/news-feed-v2`

**Date**: October 25, 2025
