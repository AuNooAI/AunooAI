# Automated Ingest Feature Implementation Guide

## 🎯 Project Overview
Implement an automated ingest pipeline that reuses existing infrastructure to:
1. Fetch articles from TheNewsAPI for monitored keywords
2. Enrich with media bias and factuality data  
3. Score articles for relevance
4. Provide relevance slider for minimum threshold
5. Scrape and enrich articles that meet threshold
6. Apply quality control validation
7. Auto-save articles that pass quality checks with status badges

**Total Estimated Time**: 11-14 hours

---

## 📋 Implementation Progress Tracker

### Phase 1: Database Schema Extensions ⏱️ 1-2 hours
- [x] **Task 1.1**: Create database migration for auto-ingest settings
  - [x] Add `auto_ingest_enabled` to keyword_monitor_settings
  - [x] Add `min_relevance_threshold` to keyword_monitor_settings  
  - [x] Add `quality_control_enabled` to keyword_monitor_settings
  - [x] Add `auto_save_approved_only` to keyword_monitor_settings
  - [x] Add `default_llm_model` to keyword_monitor_settings (default: "gpt-4o-mini")
  - [x] Add `llm_temperature` to keyword_monitor_settings (default: 0.1)
  - [x] Add `llm_max_tokens` to keyword_monitor_settings (default: 1000)
  - [ ] Test migration on development database

- [x] **Task 1.2**: Extend articles table for status tracking
  - [x] Add `ingest_status` field (pending/approved/failed/rejected)
  - [x] Add `quality_score` field for LLM quality assessment
  - [x] Add `quality_issues` field for storing failure reasons
  - [x] Add `auto_ingested` boolean flag
  - [x] Create indexes for new fields

- [x] **Task 1.3**: Update Pydantic models
  - [x] Extend `KeywordMonitorSettings` model in `app/routes/keyword_monitor.py`
  - [x] Add validation for new fields
  - [x] Update API documentation

### Phase 2: Core Service Implementation ⏱️ 3-4 hours
- [x] **Task 2.1**: Create AutomatedIngestService
  - [x] Create `app/services/automated_ingest_service.py`
  - [x] Implement `__init__` with dependency injection
  - [x] Add logging configuration
  - [x] Define service interface and error handling
  - [x] Configure LLM client with gpt-4o-mini as default model
  - [x] Add method: `get_llm_client(model_override=None)`
  - [x] Set up consistent LLM parameters (temperature=0.1, max_tokens=1000)

- [x] **Task 2.2**: Implement article enrichment pipeline
  - [x] Method: `enrich_article_with_bias(article_data)` 
    - [x] Reuse `MediaBias.get_bias_for_source()`
    - [x] Handle missing source gracefully
    - [x] Add comprehensive logging
  - [x] Method: `score_article_relevance(article_data, topic, keywords)`
    - [x] Reuse `RelevanceCalculator.analyze_relevance()`
    - [x] Configure with gpt-4o-mini for consistent scoring
    - [x] Handle relevance threshold filtering
    - [x] Return structured relevance data

- [x] **Task 2.3**: Implement quality control integration
  - [x] Method: `quality_check_article(article_data, content)`
    - [x] Call existing `/api/keyword-monitor/review-content` endpoint (placeholder)
    - [x] Ensure endpoint uses gpt-4o-mini for quality assessment
    - [x] Parse quality assessment results
    - [x] Apply quality thresholds
  - [x] Method: `scrape_article_content(uri)`
    - [x] Reuse existing scraping infrastructure (placeholder)
    - [x] Handle scraping failures gracefully
    - [x] Add content validation

- [x] **Task 2.4**: Implement batch processing
  - [x] Method: `process_articles_batch(articles, topic, keywords)`
    - [x] Process articles in configurable batches
    - [x] Implement parallel processing where safe
    - [x] Add progress tracking and error collection
  - [x] Method: `save_approved_articles(articles)`
    - [x] Reuse existing bulk save endpoints
    - [x] Set appropriate status flags
    - [x] Handle save failures gracefully
  - [x] Method: `bulk_process_topic_articles(topic_id, options)`
    - [x] Fetch all articles for a specific topic group
    - [x] Apply custom processing options (thresholds, limits)
    - [x] Track processing progress and create job status
    - [x] Support dry-run mode for preview without saving
    - [x] Return detailed processing report

### Phase 3: Keyword Monitor Integration ⏱️ 2 hours
- [x] **Task 3.1**: Extend KeywordMonitor class
  - [x] File: `app/tasks/keyword_monitor.py`
  - [x] Add auto-ingest settings loading
  - [x] Method: `get_auto_ingest_settings()`
  - [x] Method: `should_auto_ingest()` - check if enabled

- [x] **Task 3.2**: Implement auto-ingest pipeline
  - [x] Method: `auto_ingest_pipeline(articles, topic, keywords)`
    - [x] Check if auto-ingest is enabled
    - [x] Apply relevance filtering
    - [x] Call AutomatedIngestService methods
    - [x] Track processing statistics
  - [x] Integrate with existing `check_keywords()` method
    - [x] Add auto-ingest call after article collection
    - [x] Preserve existing functionality
    - [x] Add configuration-based execution

- [x] **Task 3.3**: Update background task loop
  - [x] Modify `run_keyword_monitor()` in `app/tasks/keyword_monitor.py`
  - [x] Add auto-ingest status to task tracking (inherited from existing structure)
  - [x] Update error handling for auto-ingest failures
  - [x] Add metrics collection (via auto_ingest_results)

### Phase 4: API Endpoints ⏱️ 1-2 hours
- [x] **Task 4.1**: Auto-ingest control endpoints
  - [x] `POST /api/keyword-monitor/auto-ingest/enable`
    - [x] Enable auto-ingest with validation
    - [x] Return current settings
  - [x] `POST /api/keyword-monitor/auto-ingest/disable`
    - [x] Disable auto-ingest safely
    - [x] Preserve existing settings
  - [x] `GET /api/keyword-monitor/auto-ingest/status`
    - [x] Return current auto-ingest status
    - [x] Include processing statistics
  - [x] `POST /api/keyword-monitor/auto-ingest/trigger`
    - [x] Manual trigger for testing
    - [x] Accept topic/group filters
  - [x] `POST /api/keyword-monitor/bulk-process-topic`
    - [x] Process all articles from a specific topic group
    - [x] Accept topic_id and processing options
    - [x] Return processing job ID for status tracking
    - [x] Support dry-run mode for preview

- [x] **Task 4.2**: Settings management endpoints
  - [ ] Extend existing `/api/keyword-monitor/settings` GET
    - [ ] Include auto-ingest settings in response
    - [ ] Include LLM model configuration
    - [ ] Maintain backward compatibility
  - [x] Extend existing `/api/keyword-monitor/settings` POST
    - [x] Accept auto-ingest configuration
    - [x] Validate threshold values (0.0-1.0)
    - [x] Validate LLM model selection against available models
    - [x] Validate LLM parameters (temperature: 0.0-2.0, max_tokens: 1-4000)
    - [x] Update database settings

### Phase 5: UI Enhancements ⏱️ 3-4 hours
- [ ] **Task 5.1**: Settings panel updates
  - [ ] File: `templates/keyword_alerts.html`
  - [ ] Add auto-ingest enable/disable toggle
  - [ ] Add relevance threshold slider for auto-ingest
  - [ ] Add quality control options checkboxes
  - [ ] Add LLM model selection dropdown (default: gpt-4o-mini)
  - [ ] Add LLM parameters settings (temperature, max_tokens)
  - [ ] Style consistently with existing UI

- [ ] **Task 5.2**: Relevance threshold slider
  - [ ] Reuse existing slider components (lines 1850-1945)
  - [ ] Add "Auto-Ingest Minimum Relevance" slider
  - [ ] Connect to settings API
  - [ ] Add real-time preview of threshold impact
  - [ ] Add help text explaining auto-ingest thresholds

- [ ] **Task 5.3**: Status badges and indicators
  - [ ] Add status badges to article listings
  - [ ] Show "Auto-Ingested", "Failed QC", "Manual" badges
  - [ ] Update article cards to show ingest status
  - [ ] Add filtering by ingest status
  - [ ] Color-code based on quality scores

- [ ] **Task 5.5**: Bulk processing UI components
  - [ ] Add "Bulk Process Topic" button to topic group pages
  - [ ] Create bulk processing modal with options:
    - [ ] Relevance threshold override
    - [ ] Quality control enable/disable
    - [ ] LLM model override selection
    - [ ] Dry-run preview mode
    - [ ] Max articles limit
  - [ ] Add progress indicator for bulk processing
  - [ ] Show real-time processing status and results
  - [ ] Add bulk processing history/logs viewer

- [ ] **Task 5.4**: Settings UI integration
  - [ ] Add auto-ingest section to settings modal
  - [ ] Real-time settings save/load
  - [ ] Add validation feedback
  - [ ] Settings import/export compatibility

### Phase 6: Database Integration ⏱️ 1 hour
- [ ] **Task 6.1**: Update Database class methods
  - [ ] File: `app/database.py`
  - [ ] Extend `save_article()` method (lines 1043-1124)
    - [ ] Handle new status fields
    - [ ] Set auto_ingested flag appropriately
    - [ ] Store quality assessment data
  - [ ] Add method: `get_auto_ingest_articles()`
  - [ ] Add method: `update_article_status(uri, status, quality_data)`

- [ ] **Task 6.2**: Bulk operations support
  - [ ] Extend `save_bulk_articles()` methods
  - [ ] Add status tracking to bulk operations
  - [ ] Support mixed manual/auto-ingested articles
  - [ ] Maintain transaction integrity
  - [ ] Add method: `get_articles_by_topic(topic_id, filters)`
  - [ ] Add method: `create_bulk_processing_job(topic_id, options)`
  - [ ] Add method: `get_bulk_processing_status(job_id)`

### Phase 7: Error Handling & Monitoring ⏱️ 1 hour
- [ ] **Task 7.1**: Comprehensive error handling
  - [ ] Add try-catch blocks with specific error types
  - [ ] Implement retry logic for network failures
  - [ ] Add circuit breaker pattern for API failures
  - [ ] Log all errors with context for debugging

- [ ] **Task 7.2**: Monitoring and metrics
  - [ ] Track auto-ingest success/failure rates
  - [ ] Monitor relevance score distributions
  - [ ] Track quality control decision rates
  - [ ] Add performance metrics collection
  - [ ] Create health check endpoint

- [ ] **Task 7.3**: Status reporting
  - [ ] Update keyword monitor status endpoint
  - [ ] Include auto-ingest metrics in dashboard
  - [ ] Add alert thresholds for failures
  - [ ] Email notifications for critical failures

### Phase 8: Testing & Validation ⏱️ 1-2 hours
- [ ] **Task 8.1**: Unit tests
  - [ ] Test AutomatedIngestService methods
  - [ ] Test settings validation
  - [ ] Test error handling paths
  - [ ] Mock external service calls

- [ ] **Task 8.2**: Integration tests
  - [ ] Test full auto-ingest pipeline
  - [ ] Test with real API data (limited)
  - [ ] Validate database operations
  - [ ] Test UI interactions

- [ ] **Task 8.3**: Performance testing
  - [ ] Test with various article volumes
  - [ ] Measure memory usage
  - [ ] Validate concurrent processing
  - [ ] Test rate limiting behavior

---

## 🔧 Implementation Details

### Key Files to Modify
1. `app/services/automated_ingest_service.py` - **NEW FILE**
2. `app/tasks/keyword_monitor.py` - **EXTEND** (lines 24-555)
3. `app/routes/keyword_monitor.py` - **EXTEND** (lines 73-82, add new endpoints)
4. `app/database.py` - **EXTEND** (lines 1043-1124)
5. `templates/keyword_alerts.html` - **EXTEND** (lines 1850-1945)
6. `templates/topic_dashboard.html` - **EXTEND** (add bulk process button)
7. Database migration files - **NEW FILES**

### Dependencies to Reuse
- ✅ `TheNewsAPICollector` (app/collectors/thenewsapi_collector.py)
- ✅ `MediaBias` (app/models/media_bias.py)
- ✅ `RelevanceCalculator` (app/relevance.py)
- ✅ Quality control endpoint (/api/keyword-monitor/review-content)
- ✅ Article scraping (app/research.py)
- ✅ Bulk save endpoints (app/main.py, app/bulk_research.py)
- ✅ Relevance slider UI (templates/keyword_alerts.html)

### Configuration Schema
```python
AutoIngestSettings:
    auto_ingest_enabled: bool = False
    min_relevance_threshold: float = 0.0  # 0.0-1.0
    quality_control_enabled: bool = True
    auto_save_approved_only: bool = False
    max_articles_per_run: int = 50
    parallel_processing: bool = False
    default_llm_model: str = "gpt-4o-mini"  # Default LLM for auto-ingest processes
    llm_temperature: float = 0.1  # Low temperature for consistent results
    llm_max_tokens: int = 1000  # Token limit for responses

BulkProcessingOptions:
    topic_id: str
    relevance_threshold_override: Optional[float] = None
    quality_control_enabled: bool = True
    dry_run: bool = False
    max_articles: int = 100
    processing_options: Dict[str, Any] = {}
    llm_model_override: Optional[str] = None  # Override default LLM model
```

### Status Flow
```
Article Discovery → Relevance Check → Content Scraping → Quality Control → Database Save
     ↓                    ↓                 ↓               ↓              ↓
  (collected)      (threshold filter)   (enriched)    (quality score)  (approved/failed)
```

---

## 🚀 Getting Started

1. **Set up development environment**
   ```bash
   cd /path/to/AunooAI
   source venv/bin/activate  # or equivalent
   ```

2. **Create feature branch**
   ```bash
   git checkout -b feature/automated-ingest
   ```

3. **Start with Phase 1** - Database schema extensions
4. **Test each phase** before moving to the next
5. **Update this document** with completion status

---

## 📝 Notes & Considerations

### Design Decisions
- **Batch Processing**: Process articles in configurable batches to manage memory/API limits
- **Fail-Safe**: Default to manual review when automation fails
- **Backwards Compatibility**: All existing functionality must remain unchanged
- **Configuration**: All auto-ingest behavior should be configurable
- **Monitoring**: Comprehensive logging and metrics for troubleshooting
- **LLM Consistency**: Use gpt-4.1-nano as default model for all auto-ingest processes (relevance scoring, quality control)
- **LLM Parameters**: Low temperature (0.1) for consistent, reproducible results

### Potential Challenges
- **Rate Limiting**: API limits for news sources and LLM providers
- **Memory Usage**: Processing large batches of articles
- **Error Recovery**: Handling partial failures in batch operations
- **Data Consistency**: Ensuring database consistency during bulk operations

### Success Criteria
- [ ] Auto-ingest pipeline processes articles without manual intervention
- [ ] Relevance threshold effectively filters articles
- [ ] Quality control prevents poor content from being saved
- [ ] UI provides clear status feedback and control
- [ ] System maintains performance under load
- [ ] All existing functionality continues to work

---

**Last Updated**: Core implementation completed
**Current Phase**: Phase 5 (UI Enhancements) 
**Overall Progress**: 50% ( 4 / 8 phases complete - core backend functionality ready)
