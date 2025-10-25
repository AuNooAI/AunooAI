# Cross-Topic Insights Implementation Status

## Completed Backend Changes (app/routes/vector_routes.py)

### ✅ 1. _IncidentTrackingRequest Model (Lines 1663-1709)
- Added `topics: Optional[List[str]]` field for multi-topic support
- Kept `topic: Optional[str]` for backward compatibility (deprecated)
- Added validator `sanitize_topics()` to enforce max 10 topics
- Added helper method `get_topics_list()` for backward compatibility

### ✅ 2. analyze_incidents() Function Cache Key (Lines 1721-1726)
- Changed from `incident_tracking_{topic}_...` to `incident_tracking_{topics_str}_...`
- Topics sorted alphabetically for consistent cache keys
- Format: `incident_tracking_AI,Cybersecurity,Quantum_2024-01-01_...`

### ✅ 3. analyze_incidents() SQL Query (Lines 1740-1771)
- Added `topic` to SELECT clause for badge display
- Single topic: Uses existing `topic = ? OR title LIKE ? OR summary LIKE ?` pattern
- Multiple topics: Uses `topic IN (?, ?, ...) OR (title LIKE ? OR summary LIKE ?) ...` pattern
- Backward compatible with single topic queries

### ✅ 4. analyze_incidents() Cache Operations (Lines 1788-1801, 2200-2228, 2276-2300)
- Updated cache retrieval to use `analysis_type=f"incident_tracking_{topics_str}"`
- Updated cache save metadata to include `topics`, `topics_str` instead of single `topic`
- Log messages now show topics_str instead of single topic

### ✅ 5. Error Messages (Line 1781)
- Updated "No articles found" message to show all selected topics

## Pending Frontend Changes (templates/news_feed.html)

### 🔲 1. Convert Topic Selector to Multi-Select (Lines 1172-1175)
**Current:**
```html
<select id="topic-select" class="form-select form-select-sm">
    <option value="">All Topics</option>
</select>
```

**Needed:**
```html
<div class="dropdown">
    <button class="btn btn-sm btn-outline-primary dropdown-toggle" type="button" id="topic-select-btn" data-bs-toggle="dropdown">
        <span id="topic-select-label">Select Topics</span>
    </button>
    <ul class="dropdown-menu" id="topic-select-dropdown">
        <li><a class="dropdown-item" href="#" onclick="selectAllTopics(); return false;">
            <i class="fas fa-check-double"></i> Select All
        </a></li>
        <li><a class="dropdown-item" href="#" onclick="clearAllTopics(); return false;">
            <i class="fas fa-times"></i> Clear All
        </a></li>
        <li><hr class="dropdown-divider"></li>
        <!-- Topics will be dynamically added here with checkboxes -->
    </ul>
</div>
<div id="selected-topics-badges" class="mt-2"></div>
```

### 🔲 2. Add JavaScript Helper Functions
```javascript
// Get selected topics as array
function getSelectedTopics() {
    const checkboxes = document.querySelectorAll('#topic-select-dropdown input[type="checkbox"]:checked');
    return Array.from(checkboxes).map(cb => cb.value);
}

// Update topic selector display
function updateTopicSelectorDisplay() {
    const selected = getSelectedTopics();
    const label = document.getElementById('topic-select-label');
    const badgesDiv = document.getElementById('selected-topics-badges');

    if (selected.length === 0) {
        label.textContent = 'Select Topics';
        badgesDiv.innerHTML = '';
    } else if (selected.length === 1) {
        label.textContent = selected[0];
        badgesDiv.innerHTML = `<span class="badge bg-primary">${selected[0]}</span>`;
    } else {
        label.textContent = `${selected.length} topics selected`;
        badgesDiv.innerHTML = selected.map(t =>
            `<span class="badge bg-primary me-1">${t} <i class="fas fa-times ms-1" onclick="removeTopicFromSelection('${t}'); return false;"></i></span>`
        ).join('');
    }
}

// Select all topics
function selectAllTopics() {
    document.querySelectorAll('#topic-select-dropdown input[type="checkbox"]').forEach(cb => cb.checked = true);
    updateTopicSelectorDisplay();
}

// Clear all topics
function clearAllTopics() {
    document.querySelectorAll('#topic-select-dropdown input[type="checkbox"]').forEach(cb => cb.checked = false);
    updateTopicSelectorDisplay();
}

// Remove specific topic from selection
function removeTopicFromSelection(topic) {
    document.querySelector(`#topic-select-dropdown input[value="${topic}"]`).checked = false;
    updateTopicSelectorDisplay();
}
```

### 🔲 3. Update loadIncidentTracking() Function (Line 10152)
**Current:**
```javascript
async function loadIncidentTracking(topic, startDate, endDate, daysLimit, forceRegenerate = false) {
    // ...
    let requestBody = {
        topic: topic,
        max_articles: 100,
        // ...
    };
}
```

**Needed:**
```javascript
async function loadIncidentTracking(topics, startDate, endDate, daysLimit, forceRegenerate = false) {
    // topics is now an array
    let requestBody = {
        topics: topics,  // Send array instead of single topic
        max_articles: 100,
        // ...
    };

    // Update cache key logic to sort topics for consistency
    const topicsStr = topics.length > 0 ? topics.slice().sort().join(',') : 'all_topics';
    const cacheKey = `incident_tracking_${topicsStr}_${startDate || 'no_start'}_${endDate || 'no_end'}_${daysLimit || 14}`;
}
```

### 🔲 4. Update generateInsights() Function (Line 10696)
**Current:**
```javascript
const selectedTopic = document.getElementById('topic-select').value.trim();
```

**Needed:**
```javascript
const selectedTopics = getSelectedTopics(); // Returns array
```

Then update the calls to load functions:
```javascript
await Promise.all([
    loadArticleInsights(selectedTopics, startDate, endDate, daysLimit, forceRegenerate),
    loadCategoryInsights(selectedTopics, startDate, endDate, daysLimit, forceRegenerate),
    loadIncidentTracking(selectedTopics, startDate, endDate, daysLimit, forceRegenerate)
]);
```

### 🔲 5. Add Topic Badges to Incident Cards (Line ~10500)
**In renderIncidentTracking():**
```javascript
// Add topic badge to each incident card
const topicBadge = incident.topic ?
    `<span class="badge" style="background-color: ${getTopicColor(incident.topic)}">${incident.topic}</span>` :
    '';

// Add to card header
cardHTML = `
    <div class="insight-item-card">
        <div class="d-flex justify-content-between align-items-start mb-2">
            <h6>${incident.name}</h6>
            ${topicBadge}
        </div>
        ...
    </div>
`;
```

**Add topic color mapping:**
```javascript
function getTopicColor(topic) {
    const colors = {
        'AI': '#3498db',
        'Cybersecurity': '#e74c3c',
        'Quantum': '#9b59b6',
        'Blockchain': '#f39c12',
        'Cloud': '#1abc9c'
    };
    // Generate hash-based color for unknown topics
    return colors[topic] || `hsl(${hashCode(topic) % 360}, 70%, 50%)`;
}

function hashCode(str) {
    let hash = 0;
    for (let i = 0; i < str.length; i++) {
        hash = str.charCodeAt(i) + ((hash << 5) - hash);
    }
    return Math.abs(hash);
}
```

## Database Changes

### 🔲 Add Index for Performance (Optional but Recommended)
```sql
CREATE INDEX IF NOT EXISTS idx_articles_topic_date
ON articles(topic, publication_date DESC);
```

Run via:
```bash
cd /home/orochford/tenants/multi.aunoo.ai
sqlite3 tenants.db < create_topic_index.sql
```

## Testing Checklist

- [ ] Single topic selection works (backward compatibility)
- [ ] Two topics selected (e.g., "AI" + "Cybersecurity")
- [ ] Three or more topics selected
- [ ] Cache hits work for multi-topic combinations
- [ ] Cache misses trigger new analysis
- [ ] Topic badges appear on incident cards
- [ ] Topic badges have different colors
- [ ] Performance is acceptable (< 30 seconds for 3 topics)
- [ ] Error handling for no articles found
- [ ] UI shows selected topics clearly

## Deployment Steps

1. Backend is already updated and deployed
2. Update frontend JavaScript in `templates/news_feed.html`
3. Test on multi.aunoo.ai
4. Monitor logs for any errors
5. Verify cache is working correctly
6. Optional: Add database index for performance

## Rollback Plan

If issues occur:
1. The backend is backward compatible - single topic queries still work
2. Frontend can be reverted to single-select dropdown
3. No database schema changes, so no migrations needed
