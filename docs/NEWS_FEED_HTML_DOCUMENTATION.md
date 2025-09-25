# News Feed HTML Documentation

## Overview

`templates/news_feed.html` is the main frontend interface for the Narrative Explorer application. It provides a comprehensive news analysis platform with article browsing, AI-powered insights, threat hunting capabilities, and research tools.

## File Structure

### Template Inheritance
- **Extends**: `base.html`
- **Block**: `content` - Main application content
- **Extra JS**: Marked.js for markdown rendering

### Major Sections

1. **CSS Styles** (Lines 10-686)
2. **HTML Structure** (Lines 688-1170)
3. **Modals** (Lines 1122-1233)
4. **JavaScript Functionality** (Lines 1235-8466)

## CSS Styling

### Design Philosophy
- **Techmeme-inspired minimalist design**
- **Bootstrap-based responsive layout**
- **Clean typography with system fonts**

### Key Style Components

#### Layout Styles
```css
.news-feed-container    /* Main container with max-width 1000px */
.news-header           /* Header with bottom border */
.news-nav              /* Navigation tabs styling */
```

#### Article Display
```css
.story-item            /* Individual article containers */
.story-headline        /* Article titles */
.story-meta            /* Source and date information */
```

#### Metadata Badges
```css
.bias-badge            /* Political bias indicators */
.factuality-badge      /* Factual reporting quality */
.metadata-tag          /* Category, sentiment, etc. */
```

#### Insights Interface
```css
.insight-item-card     /* Cards for insights display */
.insights-nav          /* Sub-navigation for insights tabs */
.thematic-cluster      /* Special styling for theme clusters */
```

## HTML Structure

### Main Navigation
```html
<ul class="nav nav-tabs" id="news-tabs">
    <li class="nav-item">Articles</li>
    <li class="nav-item">Six Articles</li>
    <li class="nav-item">Insights</li>
</ul>
```

### Configuration Panel
- **Date Range Selector**: 24h, 7d, 30d, 3m, 1y, all, custom
- **Topic Selector**: Dropdown populated from API
- **Model Selector**: AI model for analysis
- **Profile Selector**: Organizational analysis profiles

### Content Tabs

#### 1. Articles Tab
- **Article List**: Paginated article display
- **Filtering**: By bias, factuality, category
- **Detailed View**: Expandable article analysis
- **Research Tools**: Auspex integration buttons

#### 2. Six Articles Tab
- **Strategic Analysis**: AI-generated executive summary
- **CEO Daily Format**: Executive-focused insights
- **Research Options**: Deep dive, consensus, timeline analysis

#### 3. Insights Tab
- **Sub-navigation**: Article Insights, Category Analysis, Incident Tracking, Real-time Signals
- **Smart Button**: Context-aware generate/cache indicator
- **AI Analysis**: LLM-powered insights and research

### Modals

#### Signal Management
```html
<div class="modal" id="addSignalModal">
    <!-- Form for creating custom threat hunting signals -->
</div>
```

#### Feed Management
```html
<div class="modal" id="saveFeedModal">
    <!-- Save current feed configuration -->
</div>
<div class="modal" id="savedFeedsModal">
    <!-- View and load saved feeds -->
</div>
```

## JavaScript Functionality

### Core Application Logic

#### 1. Initialization (Lines 1236-1391)
```javascript
document.addEventListener('DOMContentLoaded', function() {
    // Date initialization
    // Model persistence
    // Profile management
    // Tab handlers
    // Auto-load configuration
});
```

#### 2. Article Management (Lines 2068-4871)

**Key Functions:**
- `loadArticles(page)` - Load paginated articles from API
- `renderArticles(articlesData)` - Display articles with metadata
- `toggleArticleDetails(uri, button)` - Expand/collapse detailed view
- `generateArticleAnalysis(uri)` - AI analysis of individual articles

**Features:**
- **Pagination**: Client-side and server-side
- **Filtering**: By bias, factuality, category, search terms
- **Sorting**: Multiple sort options (date, category, bias)
- **Caching**: Database and localStorage analysis cache
- **Exclusion**: Hide unwanted articles

#### 3. Six Articles Analysis (Lines 2170-2651)

**Key Functions:**
- `loadSixArticles()` - Generate strategic article selection
- `renderSixArticles(articles)` - Display CEO Daily format
- `launchSixArticleDeepDive()` - Executive deep dive analysis

**Features:**
- **CEO Daily Format**: Executive-focused analysis
- **Strategic Indicators**: Time horizon, risk/opportunity assessment
- **Research Integration**: Multiple Auspex analysis types

#### 4. Insights System (Lines 6057-7709)

**Core State Management:**
```javascript
let insightsState = {
    hasArticleCache: false,
    hasCategoryCache: false, 
    hasIncidentCache: false,
    isLoading: false
};
```

**Key Functions:**
- `smartGenerateInsights()` - Unified insights generation
- `checkInsightsCache()` - Cache state verification
- `autoLoadCachedInsights()` - Automatic cache loading

**Sub-modules:**
- **Article Insights**: Thematic analysis of articles
- **Category Analysis**: Distribution and trends by category
- **Incident Tracking**: Threat hunting and entity tracking
- **Real-time Signals**: Custom monitoring instructions

#### 5. Auspex Research Integration (Lines 4964-7044)

**Research Types:**
- **Theme Research**: `launchAuspexResearch(theme, sourceUri)`
- **Deep Dive**: `launchAuspexDeepDive(articleUri)`
- **Consensus Analysis**: `launchConsensusAnalysis(articleUri)`
- **Timeline Analysis**: `launchTimelineAnalysis(articleUri)`
- **Article Chat**: `launchAuspexChat(articleUri)`

**Unified Launch Function:**
```javascript
async function launchAuspexWithPrompt(chatId, prompt, model, topic, analysisType) {
    // Creates chat session
    // Sends research prompt
    // Opens modal with loading state
    // Enables follow-up chat
}
```

**Research From Insights:**
```javascript
async function launchAuspexResearchFromInsight(insightTopic, insightType) {
    // Supports: category, incident, signal_investigation, 
    //          article_theme, thematic_cluster, investigation_lead
    // Generates specialized research prompts
    // Uses launchAuspexWithPrompt for consistency
}
```

#### 6. Signal Management (Lines 7277-8264)

**Signal Instructions:**
- `showAddSignalModal()` - Create custom monitoring rules
- `saveSignalInstruction()` - Persist signal configuration
- `loadSignalInstructions()` - Display active signals
- `deleteSignalInstruction()` - Remove signals

**Signal Execution:**
- `runSingleSignal(id)` - Execute specific signal
- `runAllSignals()` - Execute all active signals
- `loadSignalAlerts()` - Display flagged articles

**Configuration:**
- **Topic Selection**: Target specific topics or global
- **Date Range**: Configurable lookback period
- **Article Tagging**: Automatic flagging of matching articles

#### 7. Incident Tracking (Lines 7485-7630)

**Core Functions:**
- `loadIncidentTracking()` - Generate incident analysis
- `renderIncidentTracking()` - Display incidents with metadata

**Features:**
- **Entity Tracking**: Organizations, individuals, events
- **Investigation Leads**: Clickable research buttons (NEW)
- **Timeline Analysis**: Event sequencing
- **Threat Assessment**: Significance and type classification

**Investigation Leads (Enhanced):**
```javascript
// Investigation leads are now clickable Auspex research buttons
leadsHtml = `
    <div class="d-flex gap-1 flex-wrap mt-1">
        ${incident.investigation_leads.map(lead => `
            <button class="btn btn-sm btn-outline-info" 
                    onclick="launchAuspexResearchFromInsight('${escapeHTML(lead)}', 'investigation_lead')">
                <i class="fas fa-search me-1"></i>${escapeHTML(lead)}
            </button>
        `).join('')}
    </div>
`;
```

### Utility Functions

#### Date and Time Management
- `handleDateRangeChange()` - Process date range selections
- `setSelectedDate()` - Update selected date and reload content
- `loadAvailableDates()` - Fetch calendar data from API

#### Cache Management
- `checkCachedAnalysisIndicators()` - Show cache status
- `clearInsightsContent()` - Reset insights when parameters change
- `clearRealTimeSignalsCache()` - Clear signal cache on instruction changes

#### UI Helpers
- `escapeHTML()` - Sanitize user input
- `showNotification()` - Toast notifications
- `updateInsightsButton()` - Smart button state management
- `getBiasClass()`, `getFactualityClass()` - CSS class helpers

### Data Flow

#### 1. Article Loading Flow
```
User selects date/topic → autoLoadArticles() → API call → renderArticles() → Cache check → Display
```

#### 2. Insights Generation Flow
```
User clicks Generate → smartGenerateInsights() → checkInsightsCache() → 
    loadArticleInsights() + loadCategoryInsights() + loadIncidentTracking() → 
    API calls with caching → Render results
```

#### 3. Research Launch Flow
```
User clicks research button → launchAuspexResearchFromInsight() → 
    Create chat session → Generate specialized prompt → launchAuspexWithPrompt() → 
    Open modal → Display loading → Show results
```

#### 4. Signal Processing Flow
```
Configure signals → runAllSignals() → API analysis → Generate alerts → 
    Tag articles → Display in alerts dashboard → Enable research
```

## API Integration

### Endpoints Used

#### News Feed APIs
- `GET /api/news-feed/articles` - Paginated article retrieval
- `GET /api/news-feed/six-articles` - Strategic article selection
- `GET /api/news-feed/available-dates` - Calendar data

#### Dashboard APIs  
- `GET /api/dashboard/article-insights/{topic}` - Thematic analysis
- `GET /api/dashboard/category-insights/{topic}` - Category distribution

#### Vector APIs
- `POST /api/incident-tracking` - Threat hunting analysis
- `POST /api/real-time-signals` - Signal processing
- `GET /api/signal-instructions` - Signal management
- `POST /api/run-signals` - Execute monitoring

#### Auspex APIs
- `POST /api/auspex/chat/sessions` - Create research sessions
- `POST /api/auspex/chat/message` - Send research prompts
- `GET /api/auspex/chat/sessions/{id}/messages` - Get responses

#### Analysis APIs
- `POST /api/vector-summary-raw` - Article analysis
- `GET /api/analysis-cache` - Cache retrieval
- `POST /api/save-analysis-cache` - Cache storage

### Request Patterns

#### Standard API Call Pattern
```javascript
const response = await fetch('/api/endpoint', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(requestData)
});

if (!response.ok) {
    throw new Error(`HTTP ${response.status}: ${response.statusText}`);
}

const data = await response.json();
```

#### Cache-First Pattern
```javascript
// 1. Check database cache
const cacheResponse = await fetch(`/api/analysis-cache?params`);
if (cacheResponse.ok && cacheData.cached) {
    return cachedResults;
}

// 2. Make API call
const response = await fetch('/api/endpoint');
const data = await response.json();

// 3. Cache results
await fetch('/api/save-analysis-cache', {
    method: 'POST',
    body: JSON.stringify(cacheData)
});
```

## Key Features

### 1. Smart Insights System
- **Unified Button**: Context-aware "Generate Insights" vs "Using Cached Data"
- **Auto-loading**: Cached insights load automatically on tab selection
- **Force Regenerate**: Available via dropdown for fresh analysis

### 2. Comprehensive Research Integration
- **Multiple Research Types**: Deep dive, consensus, timeline, chat
- **Specialized Prompts**: Tailored for each research context
- **Investigation Leads**: Clickable buttons for incident follow-up
- **Consistent Interface**: All research uses `launchAuspexWithPrompt()`

### 3. Advanced Article Management
- **Multi-level Display**: Compact view → Detailed view → Research tools
- **Smart Caching**: Database-first with localStorage fallback
- **Real-time Indicators**: Cache status, signal flags, starred articles
- **Flexible Filtering**: Multiple criteria with real-time updates

### 4. Threat Hunting Capabilities
- **Custom Signals**: User-defined monitoring instructions
- **Incident Tracking**: AI-powered entity and event detection
- **Investigation Workflows**: From detection → analysis → research
- **Alert Management**: Acknowledgment and pagination

## Error Handling

### Pattern Used Throughout
```javascript
try {
    // API operation
    const response = await fetch('/api/endpoint');
    if (!response.ok) {
        throw new Error(`HTTP ${response.status}: ${response.statusText}`);
    }
    // Success handling
} catch (error) {
    console.error('Operation failed:', error);
    showNotification(`Failed: ${error.message}`, 'error');
    // Graceful degradation
}
```

### Fallback Strategies
- **Cache Failures**: Proceed with API calls
- **API Failures**: Show user-friendly messages
- **Analysis Failures**: Provide basic metadata analysis
- **Modal Issues**: Store pending actions for later execution

## Performance Optimizations

### 1. Caching Strategy
- **Database Cache**: Primary cache with 7-day expiration
- **localStorage**: Fallback for offline capability
- **Cache Keys**: Include all relevant parameters
- **Smart Invalidation**: Clear cache when parameters change

### 2. Lazy Loading
- **Tab Content**: Load only when accessed
- **Detailed Views**: Generate analysis on expansion
- **Research Themes**: Load on demand
- **Related Articles**: Fetch when needed

### 3. Pagination
- **Client-side**: For filtered results
- **Server-side**: For large datasets
- **Smart Limits**: Adjust based on content type

## Integration Points

### 1. Auspex Chat System
- **Session Management**: Create and switch between research sessions
- **Modal Integration**: Seamless research launch
- **Context Passing**: Article and topic information
- **Real-time Updates**: No polling, uses chat interface

### 2. Backend APIs
- **News Feed Service**: Article retrieval and filtering
- **Dashboard Service**: Insights and analytics
- **Vector Service**: Similarity and clustering
- **Auspex Service**: Research and analysis

### 3. Database Integration
- **Analysis Cache**: Persistent result storage
- **Signal Alerts**: Threat hunting results
- **Article Metadata**: Rich tagging and classification

## Configuration Management

### Persistent Settings
```javascript
// Saved to localStorage
- newsFeedDefaultModel    // Selected AI model
- newsFeedTopic          // Current topic filter
- newsFeedProfileId      // Organizational profile
- newsFeedDefaults       // Complete settings snapshot
- newsFeedControlsCollapsed // UI state
```

### Dynamic Configuration
- **Topic Loading**: From `/api/topics`
- **Profile Loading**: From `/api/organizational-profiles`
- **Model Selection**: Configured in frontend, passed to backend
- **Date Ranges**: Flexible calculation based on selection

## Security Considerations

### Input Sanitization
```javascript
function escapeHTML(str) {
    return String(str).replace(/[&<>"']/g, function (match) {
        return {'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#039;'}[match];
    });
}
```

### Safe URL Handling
- **Double encoding**: For URI parameters in API calls
- **XSS Prevention**: HTML escaping in dynamic content
- **CSRF Protection**: Handled by backend session management

## Research Prompt Templates

### Investigation Lead Research
```javascript
researchPrompt = `Conduct focused investigation on the lead: "${insightTopic}"

CONTEXT FROM INCIDENT TRACKING:
This investigation lead was identified through AI-powered incident analysis.

RESEARCH FOCUS: Investigation lead - "${insightTopic}"
TOPIC AREA: "${actualTopic}"

Please use your tools to:
1. Search for articles and information related to this investigation lead
2. Analyze connections to ongoing incidents or patterns
3. Identify key entities, organizations, or individuals involved
4. Assess the significance and potential implications
5. Track historical context and related developments
6. Evaluate current status and recent activities
7. Identify additional investigation angles or related leads
8. Provide actionable intelligence and next steps

Treat this as a focused investigation that could reveal broader patterns or connections.`;
```

### Category Research
```javascript
researchPrompt = `Conduct comprehensive research on the "${insightTopic}" category in ${actualTopic}.

CONTEXT FROM NEWS FEED:
Found ${categoryArticles.length} articles in this category from current feed

RESEARCH FOCUS: "${insightTopic}" category analysis

Please use your tools to:
1. Search for recent articles in the "${insightTopic}" category
2. Analyze key developments and trends in this category
3. Identify major players and organizations involved
4. Assess market implications and future outlook
5. Compare current developments to historical patterns
6. Provide strategic recommendations for decision-makers
`;
```

## Event Handling

### Tab Navigation
```javascript
// Main tabs
document.getElementById('insights-tab').addEventListener('click', async function() {
    await checkInsightsCache();
    if (cached) await autoLoadCachedInsights();
    else showInsightsWelcomeMessage();
});

// Insights sub-navigation
document.querySelectorAll('#insights-nav .nav-link').forEach(navLink => {
    navLink.addEventListener('click', function(e) {
        // Update active states
        // Show corresponding panel
    });
});
```

### Form Interactions
```javascript
// Date range changes
function handleDateRangeChange() {
    // Update display
    // Auto-reload articles
    // Clear insights cache
}

// Search with debouncing
let searchTimeout;
function handleSearchInput() {
    clearTimeout(searchTimeout);
    searchTimeout = setTimeout(() => {
        // Apply search filter
    }, 300);
}
```

## Data Structures

### Article Object
```javascript
{
    uri: string,
    title: string,
    summary: string,
    news_source: string,
    publication_date: string,
    category: string,
    sentiment: string,
    bias: string,
    factual_reporting: string,
    tags: array,
    // ... additional metadata
}
```

### Insight Objects
```javascript
// Article Insights
{
    theme_name: string,
    theme_summary: string,
    articles: array
}

// Category Insights  
{
    category: string,
    article_count: number,
    insight_text: string,
    sample_articles: array
}

// Incident Tracking
{
    name: string,
    type: string,
    significance: string,
    description: string,
    timeline: string,
    article_uris: array,
    investigation_leads: array
}
```

## Browser Compatibility

### Required Features
- **ES6+ Support**: Async/await, arrow functions, destructuring
- **Bootstrap 5**: Modal, dropdown, collapse components
- **Fetch API**: All HTTP requests
- **localStorage**: Settings persistence

### Graceful Degradation
- **Calendar**: Fallback to date picker if API fails
- **Analysis**: Metadata-based fallback if LLM fails
- **Cache**: localStorage fallback if database cache fails

## Maintenance Notes

### Adding New Research Types
1. Add display name to `displayNames` object
2. Add research prompt case in `launchAuspexResearchFromInsight()`
3. Update UI to call with new `insightType`

### Adding New Insight Panels
1. Add HTML panel structure
2. Add navigation tab
3. Create load/render functions
4. Integrate with `generateInsights()`

### Modifying Cache Behavior
1. Update cache key generation
2. Modify cache validation logic
3. Update force regenerate handling
4. Test cache invalidation scenarios

## Dependencies

### External Libraries
- **Bootstrap 5**: UI components and styling
- **Marked.js**: Markdown rendering for Auspex responses
- **Font Awesome**: Icons throughout interface

### Internal Dependencies
- **base.html**: Template inheritance
- **auspex-chat.js**: Chat interface functionality
- **Backend APIs**: All data and analysis endpoints

## Performance Metrics

### Typical Load Times
- **Article List**: ~500ms (database query)
- **Insights Generation**: ~10-30s (LLM processing)
- **Research Launch**: ~1-2s (session creation)
- **Cache Retrieval**: ~100ms (database lookup)

### Optimization Strategies
- **Parallel Loading**: Multiple insights load simultaneously
- **Progressive Enhancement**: Core features work without JS
- **Efficient Rendering**: Virtual scrolling for large lists
- **Smart Caching**: Minimize redundant API calls

This documentation covers the complete functionality of the `news_feed.html` template, including the recent enhancements for investigation leads and Auspex research integration.
