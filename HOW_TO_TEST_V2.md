# How to Test News Feed v2

## Quick Access

The new modernized News Feed interface (v2) is now available at:

```
https://your-domain.com/news-feed-v2
```

Or locally:
```
http://localhost:8000/news-feed-v2
```

## Comparison

| Version | URL | Description |
|---------|-----|-------------|
| **Original** | `/news-feed` | Current production version |
| **v2 (New)** | `/news-feed-v2` | Modernized proof of concept |

## What's New in v2?

1. **✨ Modern Card Layout** - Articles displayed in responsive 3-column grid
2. **🎨 Softer Colors** - Professional dark gray instead of pure black
3. **📱 Better Mobile** - Single column on phones, touch-friendly buttons
4. **🧭 Sticky Navigation** - Tabs stay visible while scrolling
5. **⚡ Loading States** - Skeleton screens for better perceived performance
6. **🔍 Enhanced Filters** - Chip-style filters with count badges
7. **📊 Simplified Insights** - 3 tabs instead of 4 (removed Topic Analysis)
8. **💫 Smooth Animations** - Hover effects and transitions throughout

## Testing Checklist

### Desktop Testing
- [ ] Open `/news-feed-v2` in browser
- [ ] Test article card grid layout
- [ ] Verify sticky navigation while scrolling
- [ ] Test filter interactions
- [ ] Check all 3 insight tabs (Incident Tracking, AI Themes, Real-time Signals)
- [ ] Verify news ticker animations
- [ ] Test configuration panel dropdowns

### Mobile Testing
- [ ] Open on mobile device or use browser DevTools
- [ ] Verify single-column layout
- [ ] Test horizontal scrollable tabs
- [ ] Verify touch-friendly buttons (44px min height)
- [ ] Test configuration controls (should stack vertically)
- [ ] Check news ticker on mobile

### Comparison Testing
- [ ] Open `/news-feed` and `/news-feed-v2` side-by-side
- [ ] Compare visual appearance
- [ ] Verify same functionality in both versions
- [ ] Check that all API endpoints work the same

## Technical Details

- **Template**: `templates/news_feed_new.html`
- **Route**: Added in `app/routes/news_feed_routes.py`
- **Endpoint**: `GET /news-feed-v2`
- **Authentication**: Same as original (requires session)
- **API Compatibility**: 100% - uses same endpoints

## Switching to Production

If you want to make v2 the default:

### Option 1: Simple Replacement
```bash
# Backup original
cp templates/news_feed.html templates/news_feed_backup.html

# Replace with new version
cp templates/news_feed_new.html templates/news_feed.html
```

### Option 2: Update Route
In `app/routes/news_feed_routes.py`, change line 291:
```python
# From:
return templates.TemplateResponse("news_feed.html", {

# To:
return templates.TemplateResponse("news_feed_new.html", {
```

### Option 3: Keep Both (Recommended Initially)
Keep both versions accessible:
- Original at `/news-feed`
- New at `/news-feed-v2`

Get user feedback before fully switching.

## Rollback

If you need to revert:
```bash
# Restore from backup
cp templates/news_feed_backup.html templates/news_feed.html
```

Or simply use the original route `/news-feed` which remains unchanged.

## Need Help?

- Documentation: `NEWS_FEED_V2_CHANGES.md`
- Template: `templates/news_feed_new.html`
- Route: `app/routes/news_feed_routes.py` (line 299-307)

## Browser Compatibility

Tested and works on:
- ✅ Chrome 90+
- ✅ Firefox 88+
- ✅ Safari 14+
- ✅ Edge 90+
- ✅ Mobile browsers (iOS Safari, Android Chrome)

Uses modern CSS (Grid, Custom Properties, Flexbox) but with graceful degradation for older browsers.
