# Article Investigator Grid Layout Fix

## Issue
Article cards were displaying in a single column and expanding content was being squashed into narrow two-column layouts.

## Root Cause
1. Grid `minmax(350px, 1fr)` was too restrictive
2. No explicit breakpoints for different screen sizes
3. Internal content (columns, flex items) were being compressed
4. Bootstrap's `list-group-item` class wasn't styled for grid layout

## Solution Applied

### 1. Improved Grid System
```css
/* More flexible grid */
grid-template-columns: repeat(auto-fit, minmax(min(100%, 400px), 1fr));

/* Explicit breakpoints */
@media (min-width: 1400px) {
    grid-template-columns: repeat(3, 1fr);  /* 3 columns on large screens */
}

@media (min-width: 992px) and (max-width: 1399px) {
    grid-template-columns: repeat(2, 1fr);  /* 2 columns on medium screens */
}

@media (max-width: 768px) {
    grid-template-columns: 1fr !important;  /* 1 column on mobile */
}
```

### 2. Prevent Content Squashing
```css
/* All child elements take full width */
.story-item > * {
    width: 100%;
}

/* Force wrapping on flex containers */
.story-item .row,
.story-item .d-flex {
    flex-wrap: wrap !important;
    gap: 8px;
}

/* Columns have minimum width to prevent compression */
.story-item .col,
.story-item .col-6,
.story-item .col-md-6 {
    min-width: 200px;  /* Desktop */
    flex: 1 1 auto;
}

/* Mobile: full width */
@media (max-width: 768px) {
    .story-item .col {
        min-width: 100%;
        flex: 1 1 100%;
    }
}
```

### 3. Handle Bootstrap Classes
```css
/* Style list-group-item to match card design */
.list-group-item {
    background: white;
    border: 1px solid var(--border-light);
    border-radius: 12px;
    padding: 20px;
    box-shadow: var(--shadow-sm);
}

/* Make list-group use grid */
.list-group {
    display: grid;
    grid-template-columns: inherit;
    gap: inherit;
}
```

### 4. Card Height Adjustment
```css
/* Changed from height: 100% to height: auto */
.story-item {
    height: auto;
    min-height: 250px;  /* Maintain minimum size */
}
```

## Result

### Desktop (>1400px)
- **3 columns** of article cards
- Each card ~400px wide minimum
- Content inside cards has room to breathe

### Tablet (992px - 1399px)
- **2 columns** of article cards
- Better use of medium screen space

### Mobile (<768px)
- **1 column** (full width)
- All internal columns stack vertically
- No horizontal squashing

## Testing

After server restart, verify:

1. **Desktop**: Open `/news-feed-v2` on wide screen
   - Should see 3 columns of cards
   - Click to expand article details
   - Internal content should NOT be squashed

2. **Resize Window**: Drag browser width smaller
   - At ~1400px: Should drop to 2 columns
   - At ~768px: Should drop to 1 column

3. **Mobile Device**: Open on phone
   - Single column layout
   - All metadata stacks vertically
   - No horizontal scrolling

## Files Modified
- `templates/news_feed_new.html` (CSS sections updated)

## Additional Notes
- Card minimum width increased from 350px to 400px for better content spacing
- Explicit `!important` on mobile grid to prevent conflicts
- Bootstrap `col-*` classes now have minimum widths to prevent crushing
- All flex containers forced to wrap (`flex-wrap: wrap !important`)
