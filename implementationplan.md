## Implementation Plan: Unified Research Agents Interface

### Phase 1: Frontend Interface Redesign

#### 1.1 Main Layout Restructure
```html
<!-- New unified layout structure -->
<div class="research-agents-container">
  <!-- Header with actions -->
  <div class="agents-header">
    <h2>Research Agents</h2>
    <div class="header-actions">
      <button class="btn btn-primary" onclick="saveAsTemplate()">Save as Template</button>
      <button class="btn btn-success" onclick="startSearch()">Start Search</button>
    </div>
  </div>

  <!-- Search Configuration Panel -->
  <div class="search-config-panel">
    <!-- Search Criteria Section -->
    <!-- Advanced Options Section -->
    <!-- Search Settings Section -->
  </div>

  <!-- Results Preview Panel -->
  <div class="results-panel">
    <!-- Recent Searches History -->
    <!-- Results Preview -->
    <!-- Schedule & Distribution -->
  </div>
</div>
```

#### 1.2 Unified Search Form
```javascript
// Replace multiple source-specific forms with single unified form
const searchConfig = {
  // Basic search criteria
  keywords: "",
  searchType: "all", // all, any, exact, boolean
  excludeWords: "",
  dateRange: { from: "", to: "" },
  
  // Source selection (multi-select)
  sources: ["newsapi", "thenewsapi", "arxiv", "bluesky"],
  
  // Source-specific options (dynamic based on selected sources)
  sourceOptions: {
    newsapi: { sortBy: "relevancy", searchIn: ["title", "description"] },
    thenewsapi: { categories: [], locale: "us" },
    arxiv: { searchFields: ["title", "abstract"], primaryCategory: "" },
    bluesky: { sortBy: "latest", limitToFollowed: false }
  },
  
  // Processing options
  processingOptions: {
    enableRelevanceScoring: true,
    enableEnrichment: false,
    autoSave: true,
    scoreThreshold: 0.6
  }
};
```

### Phase 2: Backend API Unification

#### 2.1 Unified Search API Endpoint
```python
# New endpoint: /api/unified-search
@app.post("/api/unified-search")
async def unified_search(search_request: UnifiedSearchRequest):
    """
    Single endpoint that coordinates searches across all collectors
    """
    results = []
    
    for source in search_request.sources:
        try:
            # Route to appropriate collector
            source_results = await route_to_collector(source, search_request)
            
            # Apply relevance scoring if enabled
            if search_request.processing_options.enable_relevance_scoring:
                source_results = await apply_relevance_scoring(
                    source_results, 
                    search_request.topic,
                    search_request.keywords
                )
            
            # Apply enrichment if enabled
            if search_request.processing_options.enable_enrichment:
                source_results = await apply_enrichment(source_results)
            
            results.extend(source_results)
            
        except Exception as e:
            logger.error(f"Error searching {source}: {e}")
            continue
    
    return UnifiedSearchResponse(
        results=results,
        total_count=len(results),
        source_breakdown={source: count for source, count in ...}
    )
```

#### 2.2 Search Template Management
```python
# Models for search templates
class SearchTemplate(BaseModel):
    id: Optional[str] = None
    name: str
    description: Optional[str] = None
    search_config: dict
    created_by: str
    created_at: datetime
    last_used: Optional[datetime] = None
    usage_count: int = 0

@app.post("/api/search-templates")
async def save_search_template(template: SearchTemplate):
    """Save a search configuration as a reusable template"""
    
@app.get("/api/search-templates")
async def get_search_templates():
    """Get all available search templates"""
    
@app.post("/api/search-templates/{template_id}/use")
async def use_search_template(template_id: str):
    """Load and execute a saved search template"""
```

### Phase 3: Scheduling System

#### 3.1 Scheduled Search Models
```python
class ScheduledSearch(BaseModel):
    id: Optional[str] = None
    name: str
    search_template_id: str
    schedule: dict  # cron-like scheduling config
    is_active: bool = True
    last_run: Optional[datetime] = None
    next_run: Optional[datetime] = None
    notification_settings: dict
    distribution_settings: dict

class SearchExecution(BaseModel):
    id: str
    scheduled_search_id: str
    execution_time: datetime
    status: str  # running, completed, failed
    results_count: int
    processing_stats: dict
```

#### 3.2 Background Scheduler
```python
# Integration with existing background task system
@background_task_manager.scheduled_task
async def execute_scheduled_searches():
    """Run scheduled searches and process results"""
    pending_searches = await get_pending_scheduled_searches()
    
    for search in pending_searches:
        try:
            # Execute search using unified API
            results = await unified_search(search.search_config)
            
            # Process results through relevance scoring
            if search.enable_relevance_scoring:
                scored_results = await batch_relevance_scoring(
                    results, search.topic, search.keywords
                )
            
            # Apply enrichment if configured
            if search.enable_enrichment:
                enriched_results = await batch_enrichment(scored_results)
            
            # Save results and send notifications
            await save_search_results(search.id, enriched_results)
            await send_notifications(search, enriched_results)
            
        except Exception as e:
            logger.error(f"Scheduled search {search.id} failed: {e}")
```

### Phase 4: Integration with Existing Systems

#### 4.1 Relevance Scoring Integration
```javascript
// Frontend: Add relevance scoring options to search form
function addRelevanceOptions() {
  return `
    <div class="relevance-scoring-section">
      <div class="form-check">
        <input type="checkbox" id="enableRelevanceScoring" checked>
        <label>Enable Relevance Scoring</label>
      </div>
      <div class="relevance-threshold">
        <label>Minimum Relevance Score:</label>
        <input type="range" id="relevanceThreshold" min="0" max="1" step="0.1" value="0.6">
        <span class="threshold-value">0.6</span>
      </div>
    </div>
  `;
}
```

```python
# Backend: Integrate with existing relevance scoring from keyword_alerts.html
async def apply_relevance_scoring(articles, topic, keywords):
    """Apply relevance scoring to search results"""
    scored_articles = []
    
    for article in articles:
        # Use existing relevance scoring logic
        scores = await calculate_relevance_scores(
            article_text=article.summary,
            topic=topic,
            keywords=keywords,
            model_name="gpt-4o-mini"  # or configured model
        )
        
        article.topic_alignment_score = scores.topic_alignment
        article.keyword_relevance_score = scores.keyword_relevance
        article.confidence_score = scores.confidence
        article.overall_match_explanation = scores.explanation
        
        scored_articles.append(article)
    
    return scored_articles
```

#### 4.2 Enrichment Integration
```python
# Backend: Integrate with enrichment pipeline from submit_article.html
async def apply_enrichment(articles):
    """Apply enrichment processing to articles"""
    enriched_articles = []
    
    for article in articles:
        try:
            # Use existing enrichment logic
            enrichment_result = await enrich_article(
                url=article.url,
                title=article.title,
                summary=article.summary,
                model_name="gpt-4o-mini"  # or configured model
            )
            
            # Merge enrichment data
            article.category = enrichment_result.category
            article.sentiment = enrichment_result.sentiment
            article.future_signal = enrichment_result.future_signal
            article.time_to_impact = enrichment_result.time_to_impact
            article.driver_type = enrichment_result.driver_type
            article.analysis_complete = True
            
            enriched_articles.append(article)
            
        except Exception as e:
            logger.error(f"Enrichment failed for {article.url}: {e}")
            enriched_articles.append(article)  # Include without enrichment
    
    return enriched_articles
```

### Phase 5: Enhanced Results Management

#### 5.1 Results Preview with Actions
```javascript
// Enhanced results display with processing pipeline integration
function displayUnifiedResults(results) {
  const resultsHtml = results.map(article => `
    <div class="result-item" data-article-id="${article.id}">
      <!-- Article preview -->
      <div class="article-preview">
        <h6>${article.title}</h6>
        <p class="source-info">${article.source} - ${article.publication_date}</p>
        <p class="summary">${article.summary}</p>
      </div>
      
      <!-- Relevance scores (if available) -->
      ${article.topic_alignment_score ? `
        <div class="relevance-scores">
          <span class="score-badge">Topic: ${article.topic_alignment_score.toFixed(2)}</span>
          <span class="score-badge">Keywords: ${article.keyword_relevance_score.toFixed(2)}</span>
          <span class="score-badge">Confidence: ${article.confidence_score.toFixed(2)}</span>
        </div>
      ` : ''}
      
      <!-- Enrichment status -->
      <div class="enrichment-status">
        ${article.analysis_complete ? 
          '<span class="badge bg-success">Enriched</span>' : 
          '<span class="badge bg-warning">Pending Enrichment</span>'
        }
      </div>
      
      <!-- Actions -->
      <div class="article-actions">
        <button onclick="analyzeRelevance('${article.id}')" class="btn btn-sm btn-outline-info">
          <i class="fas fa-brain"></i> Score Relevance
        </button>
        <button onclick="enrichArticle('${article.id}')" class="btn btn-sm btn-outline-primary">
          <i class="fas fa-microscope"></i> Enrich
        </button>
        <button onclick="saveArticle('${article.id}')" class="btn btn-sm btn-outline-success">
          <i class="fas fa-save"></i> Save
        </button>
      </div>
    </div>
  `).join('');
  
  document.getElementById('resultsPreview').innerHTML = resultsHtml;
}
```

### Phase 6: Database Schema Updates

#### 6.1 New Tables
```sql
-- Search templates
CREATE TABLE search_templates (
    id VARCHAR(255) PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    description TEXT,
    search_config JSON NOT NULL,
    created_by VARCHAR(255) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_used TIMESTAMP,
    usage_count INT DEFAULT 0
);

-- Scheduled searches
CREATE TABLE scheduled_searches (
    id VARCHAR(255) PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    search_template_id VARCHAR(255) REFERENCES search_templates(id),
    schedule_config JSON NOT NULL,
    is_active BOOLEAN DEFAULT TRUE,
    last_run TIMESTAMP,
    next_run TIMESTAMP,
    notification_settings JSON,
    distribution_settings JSON,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Search executions
CREATE TABLE search_executions (
    id VARCHAR(255) PRIMARY KEY,
    scheduled_search_id VARCHAR(255) REFERENCES scheduled_searches(id),
    execution_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    status VARCHAR(50) NOT NULL,
    results_count INT,
    processing_stats JSON,
    error_message TEXT
);
```
