# Multi-Topic Insights Testing Guide

## Quick Start

### 1. Restart the Service
```bash
sudo systemctl restart multi.aunoo.ai
sudo journalctl -u multi.aunoo.ai -f  # Monitor logs in another terminal
```

### 2. Navigate to News Feed
Open browser: `https://multi.aunoo.ai/news-feed`

### 3. Test Multi-Topic Selection

#### Test Case 1: Basic Multi-Select
1. Click the "Topics:" dropdown (should now be a button)
2. Verify you see:
   - "Select All" option
   - "Clear All" option
   - Divider line
   - List of topics with checkboxes
3. Select 2 topics (e.g., "AI" and "Cybersecurity")
4. Verify badges appear below dropdown
5. Verify dropdown button shows "2 topics selected"

#### Test Case 2: Generate Insights
1. Select 2-3 topics
2. Click "Generate Insights" button
3. Wait for completion (15-40 seconds expected)
4. Check "Incident Tracking" tab
5. Verify incidents from multiple topics appear
6. Look for topic diversity in article titles

#### Test Case 3: Cache Testing
1. Select same topics as Test Case 2
2. Click "Generate Insights" again
3. Should complete much faster (~2-5 seconds)
4. Look for cache indicator message at bottom

#### Test Case 4: Single Topic (Backward Compatibility)
1. Clear all topics
2. Select only one topic
3. Click "Generate Insights"
4. Should work identically to old system

#### Test Case 5: Topic Removal
1. Select 3 topics
2. Click X on one badge to remove it
3. Verify badge disappears
4. Verify dropdown updates to "2 topics selected"
5. Checkbox should be unchecked in dropdown

## Expected Behavior

### UI Elements
- ✅ Dropdown opens on click
- ✅ Checkboxes toggle on/off
- ✅ Badges appear/disappear dynamically
- ✅ Badge count updates in real-time
- ✅ "Select All" checks all boxes
- ✅ "Clear All" unchecks all boxes

### API Requests
Monitor browser DevTools Network tab for `/api/incident-tracking` POST:

**Request Body** (should contain):
```json
{
  "topics": ["AI", "Cybersecurity", "Quantum"],
  "max_articles": 100,
  "model": "gpt-4o-mini",
  "days_limit": 14,
  "force_regenerate": false
}
```

### Console Logs
Look for these in browser console (F12):

```
[IncidentTracking] topics: Array(3) ["AI", "Cybersecurity", "Quantum"]
[IncidentTracking] cacheKey: incident_tracking_AI,Cybersecurity,Quantum_no_start_no_end_14
```

### Server Logs
Monitor with `sudo journalctl -u multi.aunoo.ai -f`:

```
Cache HIT: incident tracking for AI,Cybersecurity,Quantum
-- or --
Force regenerating incident tracking for AI,Cybersecurity,Quantum
```

## Common Issues & Solutions

### Issue: Dropdown doesn't show checkboxes
**Solution**: Hard refresh browser (Ctrl+Shift+R) to clear cached HTML

### Issue: "Select a topic" warning appears
**Solution**: Ensure at least one checkbox is checked before clicking Generate

### Issue: Topics not persisting across page reloads
**Solution**: Check browser localStorage:
```javascript
// In browser console:
localStorage.getItem('newsFeedTopics')
// Should show: ["AI","Cybersecurity"]
```

### Issue: API returns error "Maximum 10 topics allowed"
**Solution**: Uncheck some topics - limit is enforced at API level

### Issue: Performance seems slow
**Expected**:
- 1 topic: 5-15 seconds
- 3 topics: 15-40 seconds
- 5+ topics: 30-60 seconds

If much slower, check:
- Server CPU usage: `htop`
- Database locks: Check multi.aunoo.ai logs
- LLM API rate limits: Check OpenAI/Anthropic dashboard

## Validation Checklist

- [ ] Multi-select dropdown appears
- [ ] Checkboxes toggle correctly
- [ ] Badges show selected topics
- [ ] "Select All" works
- [ ] "Clear All" works
- [ ] Badge X removes topic
- [ ] Single topic still works
- [ ] Two topics work
- [ ] 3+ topics work
- [ ] Cache hits detected (fast 2nd run)
- [ ] localStorage persists selection
- [ ] API receives topics array
- [ ] Server logs show correct cache keys
- [ ] No JavaScript errors in console
- [ ] No Python errors in server logs

## Performance Benchmarks

Test with 3 topics, 100 articles each:

**First Run (Cache Miss)**:
- Expected: 20-40 seconds
- Database query: ~500ms
- LLM analysis: 18-35 seconds
- Cache save: ~200ms

**Second Run (Cache Hit)**:
- Expected: 2-5 seconds
- Cache retrieval: ~100ms
- Rendering: ~1-2 seconds

## Rollback Procedure

If critical issues found:

1. **Quick Rollback** (frontend only):
   ```bash
   cd /home/orochford/tenants/multi.aunoo.ai
   git checkout templates/news_feed.html
   sudo systemctl restart multi.aunoo.ai
   ```

2. **Full Rollback** (backend + frontend):
   ```bash
   cd /home/orochford/tenants/multi.aunoo.ai
   git checkout app/routes/vector_routes.py templates/news_feed.html
   sudo systemctl restart multi.aunoo.ai
   ```

3. **Verify rollback**:
   - Topic selector should be single-select dropdown again
   - Old functionality restored

## Success Metrics

Implementation is successful if:
- ✅ All UI elements work smoothly
- ✅ Multi-topic selection processes without errors
- ✅ Performance is acceptable (< 45 seconds for 3 topics)
- ✅ Cache system works correctly
- ✅ No regression in single-topic functionality
- ✅ No JavaScript console errors
- ✅ No Python server errors

## Contact

Issues? Questions? Check:
- Implementation docs: `/home/orochford/tenants/multi.aunoo.ai/CROSS_TOPIC_IMPLEMENTATION_STATUS.md`
- Completion summary: `/home/orochford/tenants/multi.aunoo.ai/IMPLEMENTATION_COMPLETE.md`
