# Product Requirements Document: Preserve Article Metadata During Analysis Workflow

## Problem Statement

Currently, when users navigate from the Keyword Alerts dashboard (`keyword_alerts.html`) to the Article Submission page (`submit_article.html`) for analysis, critical article metadata (title, publication date, source) is lost during the transition. The system then attempts to re-extract this information using LLM processing, which is:

- **Error-prone**: LLMs may misinterpret or hallucinate metadata
- **Inefficient**: Wastes API calls and processing time on data we already have
- **Legacy overhead**: Remnant from manual-only article submission workflows
- **User frustrating**: Requires manual correction of basic metadata

## Current State Analysis

### Data Flow Issues

**From `keyword_alerts.html`:**
```html
<!-- Article data available in template -->
<td>{{ alert.article.title }}</td>
<td>{{ alert.article.publication_date }}</td>
<td>{{ alert.article.source }}</td>
<td>{{ alert.article.url }}</td>
```

**To `submit_article.html`:**
```html
<!-- Only URL is passed, metadata is lost -->
<a href="/submit-article?url={{ alert.article.url|urlencode }}&topic={{ group.topic|urlencode }}">
    <i class="fas fa-microscope"></i>
</a>
```

**Current Analysis Workflow:**
1. User clicks "Analyze" button on keyword alert
2. Only URL and topic are passed to submit_article.html
3. System attempts LLM extraction of title, source, date
4. User must manually correct errors in extracted metadata
5. User proceeds with analysis of content

## Solution Overview

Preserve and pass existing article metadata through the analysis workflow, using LLM processing only for analytical fields (category, sentiment, driver_type, etc.) rather than basic article metadata.

## Requirements

### Functional Requirements

#### FR1: Metadata Preservation in URL Transition
- **Requirement**: When redirecting from keyword alerts to article submission, pass all available article metadata as URL parameters
- **Parameters to include**:
  - `title` - Article title from search results
  - `publication_date` - Publication date from search results  
  - `source` - News source from search results
  - `url` - Article URL (existing)
  - `topic` - Topic context (existing)

#### FR2: Pre-population of Analysis Form
- **Requirement**: Submit article page must pre-populate form fields with passed metadata
- **Fields to pre-populate**:
  - Article title input field
  - Article source input field
  - Source URL input field (existing)
  - Topic selection (existing)
  - Publication date (if available in form)

#### FR3: Conditional LLM Processing
- **Requirement**: Skip LLM extraction for metadata fields that are already populated
- **Implementation**: 
  - Only call LLM for content analysis (summary, category, sentiment, etc.)
  - Use existing metadata values without re-processing
  - Preserve media bias data if available from search results

#### FR4: Fallback Mechanism
- **Requirement**: Maintain existing LLM extraction as fallback for missing metadata
- **Scenarios**:
  - Manual URL submission (no metadata available)
  - Partial metadata from search results
  - User chooses to re-extract metadata

#### FR5: Bulk Analysis Enhancement
- **Requirement**: Apply metadata preservation to bulk article analysis workflow
- **Implementation**:
  - Pass metadata for each article in bulk operations
  - Pre-populate bulk results table with known metadata
  - Skip extraction for fields with existing data

### Non-Functional Requirements

#### NFR1: URL Length Limitations
- **Constraint**: URL parameters must not exceed browser/server limits
- **Solution**: Use URL encoding and consider POST method for large metadata

#### NFR2: Data Integrity
- **Requirement**: Preserved metadata must match original search results exactly
- **Validation**: Implement checksum or validation for passed metadata

#### NFR3: Backward Compatibility
- **Requirement**: Existing manual submission workflow must continue to function
- **Implementation**: Graceful degradation when metadata parameters are missing

## Technical Implementation

### Phase 1: URL Parameter Enhancement

**Update `keyword_alerts.html` analysis buttons:**
```html
<!-- Current implementation -->
<a href="/submit-article?url={{ alert.article.url|urlencode }}&topic={{ group.topic|urlencode }}">

<!-- Enhanced implementation -->
<a href="/submit-article?{{ build_analysis_url(alert.article, group.topic) }}">
```

**Backend helper function:**
```python
def build_analysis_url(article, topic):
    params = {
        'url': article.url,
        'topic': topic,
        'title': article.title,
        'source': article.source,
        'publication_date': article.publication_date,
        'summary': article.summary  # if available
    }
    # Add media bias data if available
    if article.bias:
        params['bias'] = article.bias
    if article.factual_reporting:
        params['factual_reporting'] = article.factual_reporting
    
    return urlencode(params)
```

### Phase 2: Form Pre-population

**Update `submit_article.html` initialization:**
```javascript
document.addEventListener('DOMContentLoaded', function() {
    // Existing initialization...
    
    // Pre-populate from URL parameters
    const urlParams = new URLSearchParams(window.location.search);
    
    if (urlParams.get('title')) {
        document.getElementById('articleTitle').value = urlParams.get('title');
    }
    if (urlParams.get('source')) {
        document.getElementById('articleSource').value = urlParams.get('source');
    }
    if (urlParams.get('publication_date')) {
        document.getElementById('publicationDate').value = urlParams.get('publication_date');
    }
    
    // Store metadata to skip LLM extraction
    window.preservedMetadata = {
        title: urlParams.get('title'),
        source: urlParams.get('source'),
        publication_date: urlParams.get('publication_date'),
        summary: urlParams.get('summary'),
        bias: urlParams.get('bias'),
        factual_reporting: urlParams.get('factual_reporting')
    };
});
```

### Phase 3: Conditional Analysis Logic

**Update analysis endpoint:**
```python
@app.route('/research', methods=['POST'])
async def analyze_article():
    # Check for preserved metadata
    preserved_metadata = request.form.get('preserved_metadata')
    
    if preserved_metadata:
        # Skip extraction for preserved fields
        result = await analyze_content_only(
            url=request.form.get('articleUrl'),
            content=request.form.get('articleContent'),
            preserved_data=json.loads(preserved_metadata)
        )
    else:
        # Full analysis including metadata extraction
        result = await full_article_analysis(
            url=request.form.get('articleUrl'),
            content=request.form.get('articleContent')
        )
    
    return jsonify(result)
```

## Data Schema Updates

### URL Parameters Schema
```
/submit-article?
  url=<article_url>&
  topic=<topic_name>&
  title=<encoded_title>&
  source=<encoded_source>&
  publication_date=<iso_date>&
  summary=<encoded_summary>&
  bias=<bias_rating>&
  factual_reporting=<factual_rating>
```

### Preserved Metadata Object
```json
{
  "title": "Article title from search results",
  "source": "News source name",
  "publication_date": "2024-01-01T00:00:00Z",
  "summary": "Article summary if available",
  "bias": "Left-Center",
  "factual_reporting": "Mostly Factual",
  "mbfc_credibility_rating": "High",
  "bias_country": "USA",
  "media_type": "Website"
}
```

## User Experience Improvements

### Before (Current State)
1. User sees article in keyword alerts with correct title/date
2. Clicks "Analyze" → redirected to submit page
3. Form shows only URL, other fields empty
4. LLM attempts to extract title/date → often incorrect
5. User manually corrects extracted metadata
6. User proceeds with analysis

### After (Improved State)
1. User sees article in keyword alerts with correct title/date
2. Clicks "Analyze" → redirected to submit page
3. Form pre-populated with correct title, source, date
4. LLM processes only analytical content (category, sentiment)
5. User reviews analysis results with accurate metadata
6. User saves article with confidence in data quality

## Success Metrics

### Efficiency Metrics
- **Reduced LLM API calls**: 30-50% reduction in metadata extraction calls
- **Faster analysis time**: 20-40% reduction in processing time
- **Lower token usage**: Significant reduction in extraction-related token consumption

### Accuracy Metrics
- **Metadata accuracy**: 95%+ accuracy for title/source/date (vs current ~70-80%)
- **User correction rate**: 80% reduction in manual metadata corrections
- **Analysis completion rate**: Increased user completion of analysis workflow

### User Experience Metrics
- **User satisfaction**: Reduced frustration with metadata errors
- **Workflow efficiency**: Faster time from alert to analyzed article
- **Data consistency**: Improved consistency between alerts and analyzed articles

## Testing Strategy

### Unit Tests
- URL parameter encoding/decoding
- Metadata preservation through workflow
- Fallback to LLM extraction when metadata missing

### Integration Tests
- End-to-end workflow from keyword alerts to article analysis
- Bulk analysis with metadata preservation
- Mixed scenarios (some articles with metadata, some without)

### User Acceptance Tests
- Verify pre-populated forms display correctly
- Confirm analysis skips extraction for known fields
- Validate fallback behavior for manual submissions

## Implementation Timeline

### Phase 1 (Week 1-2): URL Enhancement
- Update keyword_alerts.html to pass metadata parameters
- Create backend helper for URL building
- Test parameter passing

### Phase 2 (Week 3-4): Form Pre-population
- Update submit_article.html to read and populate metadata
- Implement preserved metadata storage
- Test form behavior

### Phase 3 (Week 5-6): Analysis Logic
- Update analysis endpoints to use preserved metadata
- Implement conditional LLM processing
- Test analysis accuracy

### Phase 4 (Week 7-8): Testing & Refinement
- Comprehensive testing across workflows
- Performance optimization
- User acceptance testing

## Risk Mitigation

### Risk: URL Parameter Length Limits
- **Mitigation**: Implement POST-based parameter passing for large metadata
- **Fallback**: Truncate non-essential metadata if URL too long

### Risk: Data Corruption During Transfer
- **Mitigation**: Implement validation and checksums for passed metadata
- **Fallback**: Revert to LLM extraction if validation fails

### Risk: Backward Compatibility Issues
- **Mitigation**: Maintain existing workflows as fallback
- **Testing**: Comprehensive testing of manual submission paths

## Future Enhancements

### Phase 2 Features
- **Media bias preservation**: Pass complete MBFC data through workflow
- **Article content caching**: Cache article content to avoid re-fetching
- **Analysis templates**: Pre-configured analysis settings per topic

### Phase 3 Features
- **Real-time synchronization**: Keep alert metadata synced with analysis results
- **Bulk metadata editing**: Allow batch updates of preserved metadata
- **Analysis history**: Track metadata changes through analysis pipeline

---

# Step-by-Step Implementation Plan

## Implementation Overview
This plan implements metadata preservation between `keyword_alerts.html` and `submit_article.html` to eliminate LLM re-extraction of known article metadata.

## Phase 1: Backend Template Function (Week 1)

### Step 1.1: Create URL Builder Helper Function
**File**: `app/routes/keyword_monitor.py` or appropriate backend file

```python
from urllib.parse import urlencode
import html

def build_analysis_url(article, topic):
    """Build URL with all available article metadata for analysis page"""
    params = {
        'url': article.url,
        'topic': topic
    }
    
    # Add metadata if available
    if hasattr(article, 'title') and article.title:
        params['title'] = article.title
    if hasattr(article, 'source') and article.source:
        params['source'] = article.source
    if hasattr(article, 'publication_date') and article.publication_date:
        params['publication_date'] = article.publication_date
    if hasattr(article, 'summary') and article.summary:
        params['summary'] = article.summary
        
    # Add media bias data if available
    if hasattr(article, 'bias') and article.bias:
        params['bias'] = article.bias
    if hasattr(article, 'factual_reporting') and article.factual_reporting:
        params['factual_reporting'] = article.factual_reporting
    if hasattr(article, 'mbfc_credibility_rating') and article.mbfc_credibility_rating:
        params['mbfc_credibility_rating'] = article.mbfc_credibility_rating
    if hasattr(article, 'bias_country') and article.bias_country:
        params['bias_country'] = article.bias_country
    if hasattr(article, 'media_type') and article.media_type:
        params['media_type'] = article.media_type
    if hasattr(article, 'popularity') and article.popularity:
        params['popularity'] = article.popularity
    
    return urlencode(params)
```

### Step 1.2: Create Jinja2 Template Filter
**File**: `app/__init__.py` or main Flask app file

```python
@app.template_filter('build_analysis_url')
def build_analysis_url_filter(article, topic):
    """Jinja2 template filter for building analysis URLs"""
    return build_analysis_url(article, topic)
```

### Step 1.3: Test Backend URL Generation
Create test to verify URL generation works correctly:

```python
# Test script
article_data = {
    'url': 'https://example.com/article',
    'title': 'Test Article Title',
    'source': 'Test Source',
    'publication_date': '2024-01-01T00:00:00Z',
    'bias': 'Left-Center',
    'factual_reporting': 'Mostly Factual'
}

topic = 'AI Technology'
url = build_analysis_url(article_data, topic)
print(f"Generated URL: /submit-article?{url}")
```

## Phase 2: Frontend Template Updates (Week 1-2)

### Step 2.1: Update keyword_alerts.html Analysis Links
**File**: `templates/keyword_alerts.html`

**Find lines around 1449 and 3610:**
```html
<!-- Current implementation -->
<a href="/submit-article?url={{ alert.article.url|urlencode }}&topic={{ group.topic|urlencode }}" 
   class="btn btn-sm btn-outline-primary"
   title="Analyze article">
    <i class="fas fa-microscope"></i>
</a>
```

**Replace with:**
```html
<!-- Enhanced implementation with metadata preservation -->
<a href="/submit-article?{{ alert.article|build_analysis_url(group.topic) }}" 
   class="btn btn-sm btn-outline-primary"
   title="Analyze article">
    <i class="fas fa-microscope"></i>
</a>
```

### Step 2.2: Update Bulk Analysis Functions
**File**: `templates/keyword_alerts.html`

**Find and update `analyzeBulkArticles` function (around line 2807):**
```javascript
function analyzeBulkArticles(topic, groupId) {
    const articles = selectedArticles.byGroup[groupId] || [];
    if (articles.length === 0) {
        showAlert('No articles selected for analysis', 'warning');
        return;
    }
    
    // Build metadata-preserved URLs for bulk analysis
    const enrichedUrls = articles.map(article => {
        const params = new URLSearchParams({
            url: article.url,
            title: article.title || '',
            source: article.source || '',
            summary: article.summary || ''
        });
        return params.toString();
    }).join('\n');
    
    const params = new URLSearchParams({
        bulk_metadata: enrichedUrls,
        topic: topic
    });
    
    window.location.href = `/submit-article?${params.toString()}`;
}
```

### Step 2.3: Update analyzeSelectedArticles Function
**File**: `templates/keyword_alerts.html`

**Find and update around line 2820:**
```javascript
function analyzeSelectedArticles(topic, groupId) {
    const checkedBoxes = document.querySelectorAll(`[data-group-id="${groupId}"] .article-checkbox:checked`);
    
    if (checkedBoxes.length === 0) {
        showAlert('No articles selected for analysis', 'warning');
        return;
    }
    
    // Extract article data with metadata preservation
    const articleData = Array.from(checkedBoxes).map(checkbox => {
        const row = checkbox.closest('tr');
        const articleLink = row.querySelector('.article-title');
        const sourceCell = row.querySelector('.source-name');
        const titleText = articleLink ? articleLink.textContent.trim() : '';
        const sourceText = sourceCell ? sourceCell.textContent.trim() : '';
        const url = articleLink ? articleLink.href : null;
        
        if (!url) return null;
        
        const params = new URLSearchParams({
            url: url,
            title: titleText,
            source: sourceText
        });
        
        return params.toString();
    }).filter(data => data);
    
    if (articleData.length === 0) {
        showAlert('No valid articles found for analysis', 'warning');
        return;
    }
    
    // Pass bulk metadata to analysis page
    const params = new URLSearchParams({
        bulk_metadata: articleData.join('\n'),
        topic: topic
    });
    
    window.location.href = `/submit-article?${params.toString()}`;
}
```

## Phase 3: Submit Article Page Updates (Week 2-3)

### Step 3.1: Add Publication Date Field to Forms
**File**: `templates/submit_article.html`

**Find the paste content form around line 350 and add publication date field:**
```html
<div class="mb-3">
    <label for="articleSource" class="form-label">Article Source</label>
    <input type="text" class="form-control" id="articleSource" name="articleSource" required placeholder="e.g., The New York Times, TechCrunch">
</div>
<div class="mb-3">
    <label for="publicationDate" class="form-label">Publication Date</label>
    <input type="date" class="form-control" id="publicationDate" name="publicationDate" placeholder="Publication date">
</div>
<div class="mb-3">
    <label for="sourceUrl" class="form-label">Source URL</label>
    <input type="url" class="form-control" id="sourceUrl" name="sourceUrl" required placeholder="https://example.com/article">
</div>
```

### Step 3.2: Update JavaScript URL Parameter Reading
**File**: `templates/submit_article.html`

**Find the DOMContentLoaded event listener around line 880 and enhance:**
```javascript
document.addEventListener('DOMContentLoaded', function() {
    // Load data from APIs
    loadTopics();
    loadAvailableModels();
    
    // Set up custom fields
    setupCustomFields();
    
    // Load recently enriched articles
    loadRecentEnrichedArticles();
    
    // Enhanced URL parameter handling
    const urlParams = new URLSearchParams(window.location.search);
    
    // Pre-populate from URL parameters
    if (urlParams.get('url')) {
        document.getElementById('bulkUrlList').value = urlParams.get('url');
    }
    
    if (urlParams.get('topic')) {
        setTimeout(() => {
            document.getElementById('topicSelect').value = urlParams.get('topic');
        }, 500);
    }
    
    // Pre-populate metadata fields
    if (urlParams.get('title')) {
        const titleField = document.getElementById('articleTitle');
        if (titleField) titleField.value = decodeURIComponent(urlParams.get('title'));
    }
    
    if (urlParams.get('source')) {
        const sourceField = document.getElementById('articleSource');
        if (sourceField) sourceField.value = decodeURIComponent(urlParams.get('source'));
    }
    
    if (urlParams.get('publication_date')) {
        const pubDateField = document.getElementById('publicationDate');
        if (pubDateField) {
            const dateStr = urlParams.get('publication_date');
            // Convert ISO date to YYYY-MM-DD format for date input
            if (dateStr.includes('T')) {
                pubDateField.value = dateStr.split('T')[0];
            } else {
                pubDateField.value = dateStr;
            }
        }
    }
    
    // Store preserved metadata globally for use in analysis
    window.preservedMetadata = {
        title: urlParams.get('title'),
        source: urlParams.get('source'),
        publication_date: urlParams.get('publication_date'),
        summary: urlParams.get('summary'),
        bias: urlParams.get('bias'),
        factual_reporting: urlParams.get('factual_reporting'),
        mbfc_credibility_rating: urlParams.get('mbfc_credibility_rating'),
        bias_country: urlParams.get('bias_country'),
        media_type: urlParams.get('media_type'),
        popularity: urlParams.get('popularity')
    };
    
    // Handle bulk metadata if present
    if (urlParams.get('bulk_metadata')) {
        handleBulkMetadata(urlParams.get('bulk_metadata'));
    }
    
    console.log('Preserved metadata:', window.preservedMetadata);
});
```

### Step 3.3: Add Bulk Metadata Handler
**File**: `templates/submit_article.html`

**Add new function after the DOMContentLoaded event:**
```javascript
function handleBulkMetadata(bulkMetadataString) {
    try {
        const metadataLines = bulkMetadataString.split('\n');
        const urlsWithMetadata = [];
        
        metadataLines.forEach(line => {
            if (line.trim()) {
                const params = new URLSearchParams(line);
                const url = params.get('url');
                const title = params.get('title');
                const source = params.get('source');
                
                if (url) {
                    urlsWithMetadata.push({
                        url: url,
                        title: title || '',
                        source: source || ''
                    });
                }
            }
        });
        
        // Store bulk metadata for use during analysis
        window.bulkPreservedMetadata = urlsWithMetadata;
        
        // Populate URL list with just URLs
        const urlList = urlsWithMetadata.map(item => item.url).join('\n');
        document.getElementById('bulkUrlList').value = urlList;
        
        console.log('Bulk preserved metadata:', window.bulkPreservedMetadata);
    } catch (error) {
        console.error('Error parsing bulk metadata:', error);
    }
}
```

## Phase 4: Analysis Logic Updates (Week 3-4)

### Step 4.1: Update handlePasteSubmit Function
**File**: `templates/submit_article.html`

**Find and update the function around line 450:**
```javascript
async function handlePasteSubmit(event) {
    event.preventDefault();
    console.log('Paste form submission started');

    const submitButton = event.target.querySelector('button[type="submit"]');
    if (submitButton.disabled) return;
    submitButton.disabled = true;

    // Add processing indicator
    const processingIndicator = document.createElement('div');
    processingIndicator.id = 'processingIndicator';
    processingIndicator.className = 'processing-indicator';
    processingIndicator.innerHTML = `
        <div class="spinner-border text-primary" role="status">
            <span class="visually-hidden">Loading...</span>
        </div>
        <h4 class="mt-3">Analyzing article...</h4>
        <p>Please wait while we process your request.</p>
    `;
    
    document.getElementById('pasteForm').insertAdjacentElement('afterend', processingIndicator);

    // Get form data
    const articleTitle = document.getElementById('articleTitle').value;
    const articleSource = document.getElementById('articleSource').value;
    const sourceUrl = document.getElementById('sourceUrl').value;
    const publicationDate = document.getElementById('publicationDate').value;
    const pasteContent = document.getElementById('pasteContent').value;
    const topic = document.getElementById('topicSelect').value;
    const modelName = document.getElementById('modelName').value;
    const summaryType = document.getElementById('summaryType').value;
    const summaryVoice = getSummaryVoice();
    const summaryLength = getSummaryLength();

    try {
        const articleUrl = sourceUrl || `https://aunoo.ai/manual-entry/${Date.now()}`;
        
        // Prepare preserved metadata
        const preservedData = {
            title: articleTitle || window.preservedMetadata?.title,
            source: articleSource || window.preservedMetadata?.source,
            publication_date: publicationDate || window.preservedMetadata?.publication_date,
            bias: window.preservedMetadata?.bias,
            factual_reporting: window.preservedMetadata?.factual_reporting,
            mbfc_credibility_rating: window.preservedMetadata?.mbfc_credibility_rating,
            bias_country: window.preservedMetadata?.bias_country,
            media_type: window.preservedMetadata?.media_type,
            popularity: window.preservedMetadata?.popularity
        };
        
        // Analyze the article
        const formData = new FormData();
        formData.append('articleUrl', articleUrl);
        formData.append('articleContent', pasteContent);
        formData.append('selectedTopic', topic);
        formData.append('modelName', modelName);
        formData.append('summaryType', summaryType);
        formData.append('summaryVoice', summaryVoice);
        formData.append('summaryLength', summaryLength);
        formData.append('preservedMetadata', JSON.stringify(preservedData));
        
        const response = await fetch('/research', {
            method: 'POST',
            body: formData
        });

        if (!response.ok) {
            const errorData = await response.json();
            throw new Error(JSON.stringify(errorData));
        }

        const result = await response.json();
        
        // Use preserved metadata instead of extracted values
        result.title = preservedData.title || result.title;
        result.news_source = preservedData.source || result.news_source;
        result.publication_date = preservedData.publication_date || result.publication_date;
        
        // Preserve media bias data
        if (preservedData.bias) result.bias = preservedData.bias;
        if (preservedData.factual_reporting) result.factual_reporting = preservedData.factual_reporting;
        if (preservedData.mbfc_credibility_rating) result.mbfc_credibility_rating = preservedData.mbfc_credibility_rating;
        if (preservedData.bias_country) result.bias_country = preservedData.bias_country;
        if (preservedData.media_type) result.media_type = preservedData.media_type;
        if (preservedData.popularity) result.popularity = preservedData.popularity;
        
        displayAnalysisResult(result);
    } catch (error) {
        console.error('Error:', error);
        showErrorMessage(`An error occurred: ${error.message}`);
    } finally {
        removeProcessingIndicator();
        submitButton.disabled = false;
    }
}
```

### Step 4.2: Update Bulk Analysis Function
**File**: `templates/submit_article.html`

**Find and update analyzeBulkUrls function around line 1020:**
```javascript
async function analyzeBulkUrls(requestData) {
    const results = [];
    let firstChunkReceived = false;
    
    // Add preserved metadata to request if available
    if (window.bulkPreservedMetadata) {
        requestData.preservedMetadata = window.bulkPreservedMetadata;
    }
    
    const response = await fetch('/api/bulk-research-stream', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            Accept: 'application/x-ndjson'
        },
        body: JSON.stringify(requestData)
    });

    if (!response.ok || !response.body) {
        throw new Error(`Server error: ${response.status}`);
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';

    while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop();
        
        for (const line of lines) {
            if (!line.trim()) continue;
            try {
                const obj = JSON.parse(line);
                
                // Apply preserved metadata if available
                if (window.bulkPreservedMetadata) {
                    const preserved = window.bulkPreservedMetadata.find(meta => meta.url === obj.uri);
                    if (preserved) {
                        obj.title = preserved.title || obj.title;
                        obj.news_source = preserved.source || obj.news_source;
                        console.log(`Applied preserved metadata for ${obj.uri}:`, preserved);
                    }
                }
                
                results.push(obj);
                displayBulkResultRow(obj);

                if (!firstChunkReceived) {
                    const indicator = document.getElementById('bulkProcessingIndicator');
                    if (indicator) {
                        indicator.querySelector('h4').textContent = 'Receiving results...';
                    }
                    firstChunkReceived = true;
                }
            } catch (e) {
                console.error('Failed to parse NDJSON line', line, e);
            }
        }
    }

    // Parse any remaining buffer
    if (buffer.trim()) {
        try {
            const obj = JSON.parse(buffer);
            
            // Apply preserved metadata if available
            if (window.bulkPreservedMetadata) {
                const preserved = window.bulkPreservedMetadata.find(meta => meta.url === obj.uri);
                if (preserved) {
                    obj.title = preserved.title || obj.title;
                    obj.news_source = preserved.source || obj.news_source;
                }
            }
            
            results.push(obj);
            displayBulkResultRow(obj);
        } catch (e) {
            console.error('Failed to parse last NDJSON fragment', buffer, e);
        }
    }

    return results;
}
```

## Phase 5: Backend Analysis Logic Updates (Week 4-5)

### Step 5.1: Update Research Endpoint
**File**: `app/routes/research.py` (or appropriate backend file)

```python
@app.route('/research', methods=['POST'])
async def analyze_article():
    try:
        # Get preserved metadata if available
        preserved_metadata_str = request.form.get('preservedMetadata')
        preserved_metadata = {}
        
        if preserved_metadata_str:
            try:
                preserved_metadata = json.loads(preserved_metadata_str)
                print(f"Using preserved metadata: {preserved_metadata}")
            except json.JSONDecodeError:
                print("Failed to parse preserved metadata, proceeding with full analysis")
        
        # Standard analysis parameters
        article_url = request.form.get('articleUrl')
        article_content = request.form.get('articleContent')
        topic = request.form.get('selectedTopic')
        model_name = request.form.get('modelName')
        summary_type = request.form.get('summaryType')
        summary_voice = request.form.get('summaryVoice')
        summary_length = request.form.get('summaryLength')
        
        # Perform analysis with preserved metadata
        if preserved_metadata:
            result = await analyze_with_preserved_metadata(
                url=article_url,
                content=article_content,
                topic=topic,
                model_name=model_name,
                summary_type=summary_type,
                summary_voice=summary_voice,
                summary_length=summary_length,
                preserved_data=preserved_metadata
            )
        else:
            # Full analysis including metadata extraction
            result = await full_article_analysis(
                url=article_url,
                content=article_content,
                topic=topic,
                model_name=model_name,
                summary_type=summary_type,
                summary_voice=summary_voice,
                summary_length=summary_length
            )
        
        return jsonify(result)
        
    except Exception as e:
        print(f"Error in research endpoint: {str(e)}")
        return jsonify({'error': str(e)}), 500

async def analyze_with_preserved_metadata(url, content, topic, model_name, summary_type, summary_voice, summary_length, preserved_data):
    """Analyze article using preserved metadata, only extracting missing fields"""
    
    # Start with preserved metadata
    result = {
        'uri': url,
        'title': preserved_data.get('title'),
        'news_source': preserved_data.get('source'),
        'publication_date': preserved_data.get('publication_date'),
        'bias': preserved_data.get('bias'),
        'factual_reporting': preserved_data.get('factual_reporting'),
        'mbfc_credibility_rating': preserved_data.get('mbfc_credibility_rating'),
        'bias_country': preserved_data.get('bias_country'),
        'media_type': preserved_data.get('media_type'),
        'popularity': preserved_data.get('popularity')
    }
    
    # Only extract metadata that's missing
    if not result['title'] or not result['news_source']:
        print("Some metadata missing, extracting with LLM...")
        extracted_metadata = await extract_missing_metadata(url, content, model_name)
        
        if not result['title']:
            result['title'] = extracted_metadata.get('title')
        if not result['news_source']:
            result['news_source'] = extracted_metadata.get('news_source')
        if not result['publication_date']:
            result['publication_date'] = extracted_metadata.get('publication_date')
    
    # Always perform content analysis (summary, category, sentiment, etc.)
    content_analysis = await analyze_article_content(
        url=url,
        content=content,
        topic=topic,
        model_name=model_name,
        summary_type=summary_type,
        summary_voice=summary_voice,
        summary_length=summary_length
    )
    
    # Merge content analysis results
    result.update(content_analysis)
    
    return result
```

### Step 5.2: Update Bulk Research Stream Endpoint
**File**: `app/routes/bulk_research.py` (or appropriate backend file)

```python
@app.route('/api/bulk-research-stream', methods=['POST'])
async def bulk_research_stream():
    try:
        data = request.get_json()
        urls = data.get('urls', [])
        preserved_metadata = data.get('preservedMetadata', [])
        
        # Create lookup for preserved metadata
        metadata_lookup = {}
        for meta in preserved_metadata:
            if meta.get('url'):
                metadata_lookup[meta['url']] = meta
        
        # Process each URL
        for url in urls:
            try:
                preserved_data = metadata_lookup.get(url, {})
                
                if preserved_data:
                    print(f"Using preserved metadata for {url}: {preserved_data}")
                    result = await analyze_with_preserved_metadata(
                        url=url,
                        content=None,  # Will be fetched
                        topic=data.get('topic'),
                        model_name=data.get('modelName'),
                        summary_type=data.get('summaryType'),
                        summary_voice=data.get('summaryVoice'),
                        summary_length=data.get('summaryLength'),
                        preserved_data=preserved_data
                    )
                else:
                    # Full analysis for URLs without preserved metadata
                    result = await full_article_analysis(
                        url=url,
                        content=None,
                        topic=data.get('topic'),
                        model_name=data.get('modelName'),
                        summary_type=data.get('summaryType'),
                        summary_voice=data.get('summaryVoice'),
                        summary_length=data.get('summaryLength')
                    )
                
                # Stream result
                yield f"{json.dumps(result)}\n"
                
            except Exception as e:
                error_result = {
                    'uri': url,
                    'error': str(e),
                    'title': preserved_data.get('title', 'Error processing article'),
                    'news_source': preserved_data.get('source', 'Unknown')
                }
                yield f"{json.dumps(error_result)}\n"
                
    except Exception as e:
        error_result = {'error': f'Bulk analysis failed: {str(e)}'}
        yield f"{json.dumps(error_result)}\n"
```

## Phase 6: Testing and Validation (Week 5-6)

### Step 6.1: Manual Testing Checklist
- [ ] Single article analysis from keyword alerts preserves title, source, date
- [ ] Bulk article analysis preserves metadata for all selected articles  
- [ ] Manual URL submission still works without metadata
- [ ] Paste content form uses preserved metadata when available
- [ ] Media bias information is preserved through workflow
- [ ] Analysis skips metadata extraction when data is preserved
- [ ] Fallback to LLM extraction works when metadata is missing

### Step 6.2: Create Test Data
**File**: `test_metadata_preservation.py`

```python
# Test script for metadata preservation
import requests
import json

def test_single_article_analysis():
    """Test single article with preserved metadata"""
    url = "http://localhost:5000/submit-article"
    params = {
        'url': 'https://example.com/test-article',
        'topic': 'AI Technology',
        'title': 'Test Article About AI',
        'source': 'Tech News Daily',
        'publication_date': '2024-01-15',
        'bias': 'Left-Center',
        'factual_reporting': 'Mostly Factual'
    }
    
    response = requests.get(url, params=params)
    print(f"Single article test: {response.status_code}")
    return response.status_code == 200

def test_bulk_analysis():
    """Test bulk analysis with preserved metadata"""
    bulk_metadata = [
        "url=https://example.com/article1&title=Article+1&source=Source+1",
        "url=https://example.com/article2&title=Article+2&source=Source+2"
    ]
    
    url = "http://localhost:5000/submit-article"
    params = {
        'bulk_metadata': '\n'.join(bulk_metadata),
        'topic': 'AI Technology'
    }
    
    response = requests.get(url, params=params)
    print(f"Bulk analysis test: {response.status_code}")
    return response.status_code == 200

if __name__ == "__main__":
    test_single_article_analysis()
    test_bulk_analysis()
```

### Step 6.3: Performance Testing
Create performance comparison tests:

```python
import time
import requests

def measure_analysis_time(with_preserved_metadata=True):
    """Measure analysis time with and without preserved metadata"""
    start_time = time.time()
    
    if with_preserved_metadata:
        # Test with preserved metadata
        data = {
            'articleUrl': 'https://example.com/article',
            'preservedMetadata': json.dumps({
                'title': 'Preserved Title',
                'source': 'Preserved Source',
                'publication_date': '2024-01-15'
            })
        }
    else:
        # Test without preserved metadata (full extraction)
        data = {
            'articleUrl': 'https://example.com/article'
        }
    
    response = requests.post('http://localhost:5000/research', data=data)
    end_time = time.time()
    
    return end_time - start_time, response.status_code

# Compare performance
time_with_preserved, status_preserved = measure_analysis_time(True)
time_without_preserved, status_full = measure_analysis_time(False)

print(f"With preserved metadata: {time_with_preserved:.2f}s")
print(f"Without preserved metadata: {time_without_preserved:.2f}s")
print(f"Time saved: {time_without_preserved - time_with_preserved:.2f}s")
```

## Phase 7: Deployment and Monitoring (Week 6-7)

### Step 7.1: Production Deployment Checklist
- [ ] Deploy backend URL builder function
- [ ] Deploy updated templates
- [ ] Deploy updated analysis endpoints
- [ ] Test in staging environment
- [ ] Monitor error rates
- [ ] Monitor API usage reduction
- [ ] Monitor user satisfaction

### Step 7.2: Monitoring Setup
Add logging to track metadata preservation effectiveness:

```python
import logging

def log_metadata_preservation_stats(preserved_fields, extracted_fields):
    """Log statistics about metadata preservation"""
    total_fields = len(preserved_fields) + len(extracted_fields)
    preserved_count = len([f for f in preserved_fields if f])
    extraction_saved = preserved_count / total_fields * 100
    
    logging.info(f"Metadata preservation: {preserved_count}/{total_fields} fields preserved ({extraction_saved:.1f}% extraction saved)")
```

### Step 7.3: Success Metrics Collection
Set up metrics collection to measure:
- Reduction in LLM metadata extraction calls
- Improvement in metadata accuracy
- Reduction in user corrections
- Faster analysis completion times

## Success Criteria
- [ ] 90%+ of articles from keyword alerts use preserved metadata
- [ ] 30-50% reduction in LLM metadata extraction API calls
- [ ] 95%+ accuracy for title, source, and publication date
- [ ] User reports fewer metadata correction needs
- [ ] Analysis workflow completion time reduced by 20-40%

## Risk Mitigation
- Maintain fallback to full LLM extraction if metadata preservation fails
- Implement URL length monitoring and truncation if needed
- Add validation for preserved metadata integrity
- Ensure backward compatibility with existing manual submission workflows

This implementation plan provides a systematic approach to preserving article metadata throughout the analysis workflow while maintaining system reliability and backward compatibility.
